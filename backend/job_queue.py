import asyncio
import logging
import math
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# specs/007 research.md R9. Each running check holds a browser context and an index
# in memory and competes for 2 vCPU; the LLM quota (not these workers) is the real
# platform-wide ceiling, so more workers would mostly just wait on the pacer.
MAX_CONCURRENT_CHECKS = int(os.environ.get("MAX_CONCURRENT_CHECKS", "4"))
# Keeps one user from pushing everyone else back in line (spec FR-007).
MAX_ACTIVE_CHECKS_PER_USER = int(os.environ.get("MAX_ACTIVE_CHECKS_PER_USER", "2"))
# Bounds on what waits: well above 10+ users x the per-user limit, but finite so the
# queue can't exhaust memory or the task's disk (held uploads live in /tmp, which
# shares Fargate's 20 GB ephemeral storage with the image itself).
MAX_QUEUED_CHECKS = int(os.environ.get("MAX_QUEUED_CHECKS", "50"))
MAX_QUEUED_UPLOAD_BYTES = int(os.environ.get("MAX_QUEUED_UPLOAD_BYTES", str(8 * 1024**3)))

DEFAULT_CHECK_DURATION_S = 60.0
FAILED_UNEXPECTEDLY = "L’analyse a échoué à cause d’une erreur inattendue du serveur — merci de la relancer."


class QueueFull(Exception):
    pass


class UserLimitReached(Exception):
    pass


class AlreadyQueued(Exception):
    pass


@dataclass
class Job:
    analysis_id: uuid.UUID
    user_id: uuid.UUID
    run: Callable[[], Awaitable[None]]
    # The uploaded material waiting with this job (spec FR-018: temporary only) —
    # deleted once the job ends, whatever the outcome.
    held_file: Path | None = None
    held_bytes: int = 0
    # Runs after the job whatever the outcome (e.g. releasing a resumed session).
    on_finish: Callable[[], None] | None = None
    enqueued_at: float = field(default_factory=time.monotonic)


StatusRecorder = Callable[[uuid.UUID, str, str | None], None]


class JobQueue:
    """In-process FIFO of compliance checks, run by a fixed pool of workers.

    Single-instance by design (spec Assumptions): the queue, like the resumable
    sessions, lives in this process's memory.
    """

    def __init__(
        self,
        record_status: StatusRecorder,
        workers: int = MAX_CONCURRENT_CHECKS,
        max_per_user: int = MAX_ACTIVE_CHECKS_PER_USER,
        max_queued: int = MAX_QUEUED_CHECKS,
        max_held_bytes: int = MAX_QUEUED_UPLOAD_BYTES,
    ):
        self._record_status = record_status
        self.workers = workers
        self.max_per_user = max_per_user
        self._max_queued = max_queued
        self._max_held_bytes = max_held_bytes
        self._pending: deque[Job] = deque()
        self._running: dict[uuid.UUID, Job] = {}
        self._held_bytes = 0
        self._available = asyncio.Semaphore(0)
        self._tasks: list[asyncio.Task] = []
        self._average_duration = DEFAULT_CHECK_DURATION_S

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self.workers)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        # Running jobs released their uploads when cancelled; waiting ones never ran.
        while self._pending:
            self._release_held(self._pending.popleft())

    def is_active(self, analysis_id: uuid.UUID) -> bool:
        return analysis_id in self._running or any(job.analysis_id == analysis_id for job in self._pending)

    def ensure_can_enqueue(self, user_id: uuid.UUID, held_bytes: int = 0) -> None:
        active_for_user = sum(1 for job in self._running.values() if job.user_id == user_id) + sum(
            1 for job in self._pending if job.user_id == user_id
        )
        if active_for_user >= self.max_per_user:
            raise UserLimitReached
        if len(self._pending) >= self._max_queued or self._held_bytes + held_bytes > self._max_held_bytes:
            raise QueueFull

    def enqueue(self, job: Job) -> int:
        """Adds the job and returns its queue position (0 = starts right away)."""
        if self.is_active(job.analysis_id):
            raise AlreadyQueued
        self.ensure_can_enqueue(job.user_id, job.held_bytes)
        self._pending.append(job)
        self._held_bytes += job.held_bytes
        self._available.release()
        return self.position(job.analysis_id)

    def position(self, analysis_id: uuid.UUID) -> int | None:
        """1-based rank among analyses still waiting for a worker; 0 once it runs (or
        is about to, a worker being free); None if it isn't in the queue at all."""
        if analysis_id in self._running:
            return 0
        idle_workers = max(0, self.workers - len(self._running))
        for index, job in enumerate(self._pending):
            if job.analysis_id == analysis_id:
                return max(0, index + 1 - idle_workers)
        return None

    def estimate_seconds(self, position: int | None) -> int | None:
        if position is None:
            return None
        # Each "wave" of `workers` analyses ahead takes about one average run.
        return int(math.ceil(position / self.workers) * self._average_duration)

    async def _worker(self) -> None:
        while True:
            await self._available.acquire()
            job = self._pending.popleft()
            self._running[job.analysis_id] = job
            await self._run(job)

    async def _run(self, job: Job) -> None:
        started = time.monotonic()
        error: str | None = None
        try:
            self._safe_record(job.analysis_id, "running", None)
            await job.run()
        except HTTPException as exception:
            detail = exception.detail
            error = detail if isinstance(detail, str) else str(detail)
            logger.warning("Analysis %s failed: %s", job.analysis_id, error)
        except asyncio.CancelledError:
            # Shutdown: the row stays "running" and is failed by the next startup's
            # recovery (db.recover_interrupted_analyses).
            raise
        except Exception:
            logger.exception("Analysis %s failed unexpectedly", job.analysis_id)
            error = FAILED_UNEXPECTEDLY
        finally:
            self._running.pop(job.analysis_id, None)
            self._release_held(job)
            if job.on_finish is not None:
                try:
                    job.on_finish()
                except Exception:
                    logger.exception("on_finish failed for analysis %s", job.analysis_id)

        if error is None:
            self._average_duration = 0.7 * self._average_duration + 0.3 * (time.monotonic() - started)
            self._safe_record(job.analysis_id, "done", None)
        else:
            self._safe_record(job.analysis_id, "failed", error)

    def _release_held(self, job: Job) -> None:
        self._held_bytes -= job.held_bytes
        job.held_bytes = 0
        if job.held_file is not None:
            job.held_file.unlink(missing_ok=True)

    def _safe_record(self, analysis_id: uuid.UUID, status: str, error: str | None) -> None:
        # A database hiccup must not kill the worker (every later job would then wait
        # forever); the status is just left behind and recovered at next startup.
        try:
            self._record_status(analysis_id, status, error)
        except Exception:
            logger.exception("Could not record status %s for analysis %s", status, analysis_id)


def _record_status_in_db(analysis_id: uuid.UUID, status: str, error: str | None) -> None:
    # Imported here so this module (and its tests) doesn't need a database.
    from db import record_analysis_status

    record_analysis_status(analysis_id, status, error)


# The process-wide queue used by the API (main.py enqueues, history.py reports positions).
analysis_queue = JobQueue(_record_status_in_db)
