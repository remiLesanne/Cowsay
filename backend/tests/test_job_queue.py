import asyncio
import uuid

import pytest
from fastapi import HTTPException

from job_queue import FAILED_UNEXPECTEDLY, AlreadyQueued, Job, JobQueue, QueueFull, UserLimitReached


class Recorder:
    def __init__(self):
        self.events: list[tuple[uuid.UUID, str, str | None]] = []

    def __call__(self, analysis_id, status, error):
        self.events.append((analysis_id, status, error))

    def final(self, analysis_id):
        return [event for event in self.events if event[0] == analysis_id][-1][1:]


def _job(run, user_id=None, **kwargs) -> Job:
    return Job(analysis_id=uuid.uuid4(), user_id=user_id or uuid.uuid4(), run=run, **kwargs)


async def _wait_until(condition, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        assert loop.time() < deadline, "condition not reached"
        await asyncio.sleep(0.01)


def test_jobs_run_in_submission_order_and_positions_move_up():
    async def scenario():
        recorder = Recorder()
        queue = JobQueue(recorder, workers=1, max_per_user=10)
        gates = [asyncio.Event() for _ in range(3)]
        order = []

        def body(index):
            async def run():
                order.append(index)
                await gates[index].wait()
            return run

        jobs = [_job(body(index)) for index in range(3)]
        queue.start()
        positions = [queue.enqueue(job) for job in jobs]
        await _wait_until(lambda: order == [0])

        assert positions == [0, 1, 2]  # the first starts at once, a free worker being there
        assert [queue.position(job.analysis_id) for job in jobs] == [0, 1, 2]
        assert queue.estimate_seconds(2) > queue.estimate_seconds(1) > 0

        gates[0].set()
        await _wait_until(lambda: order == [0, 1])
        assert queue.position(jobs[2].analysis_id) == 1
        assert queue.position(jobs[0].analysis_id) is None

        gates[1].set()
        gates[2].set()
        await _wait_until(lambda: len(recorder.events) == 6)
        assert order == [0, 1, 2]
        assert all(recorder.final(job.analysis_id) == ("done", None) for job in jobs)
        await queue.stop()

    asyncio.run(scenario())


def test_per_user_limit_counts_waiting_and_running_jobs():
    async def scenario():
        queue = JobQueue(Recorder(), workers=1, max_per_user=2)
        user = uuid.uuid4()
        never = asyncio.Event()
        queue.start()
        queue.enqueue(_job(never.wait, user_id=user))
        queue.enqueue(_job(never.wait, user_id=user))
        with pytest.raises(UserLimitReached):
            queue.enqueue(_job(never.wait, user_id=user))
        queue.enqueue(_job(never.wait))  # other users are not affected
        await queue.stop()

    asyncio.run(scenario())


def test_queue_bounds_on_count_and_held_bytes():
    async def scenario():
        never = asyncio.Event()
        by_count = JobQueue(Recorder(), workers=1, max_queued=1)
        by_count.enqueue(_job(never.wait))  # no worker started: stays pending
        with pytest.raises(QueueFull):
            by_count.enqueue(_job(never.wait))

        by_bytes = JobQueue(Recorder(), workers=1, max_held_bytes=100)
        by_bytes.enqueue(_job(never.wait, held_bytes=60))
        with pytest.raises(QueueFull):
            by_bytes.ensure_can_enqueue(uuid.uuid4(), held_bytes=60)
        by_bytes.ensure_can_enqueue(uuid.uuid4(), held_bytes=40)

    asyncio.run(scenario())


def test_same_analysis_cannot_be_queued_twice():
    async def scenario():
        queue = JobQueue(Recorder(), workers=1)
        never = asyncio.Event()
        job = _job(never.wait)
        queue.enqueue(job)
        assert queue.is_active(job.analysis_id)
        with pytest.raises(AlreadyQueued):
            queue.enqueue(Job(analysis_id=job.analysis_id, user_id=uuid.uuid4(), run=never.wait))

    asyncio.run(scenario())


def test_failures_are_recorded_and_free_the_slot(tmp_path):
    async def scenario():
        recorder = Recorder()
        queue = JobQueue(recorder, workers=1)
        finished = []

        async def known_failure():
            raise HTTPException(status_code=502, detail="Repomix n’a pas réussi à convertir le projet")

        async def crash():
            raise RuntimeError("boom")

        async def ok():
            pass

        held = tmp_path / "upload.zip"
        held.write_bytes(b"x" * 10)
        jobs = [
            _job(known_failure, held_file=held, held_bytes=10, on_finish=lambda: finished.append(1)),
            _job(crash),
            _job(ok),
        ]
        queue.start()
        for job in jobs:
            queue.enqueue(job)
        await _wait_until(lambda: len(recorder.events) == 6)

        assert recorder.final(jobs[0].analysis_id) == ("failed", "Repomix n’a pas réussi à convertir le projet")
        assert recorder.final(jobs[1].analysis_id) == ("failed", FAILED_UNEXPECTEDLY)
        assert recorder.final(jobs[2].analysis_id) == ("done", None)
        assert not held.exists()  # held upload deleted even though the job failed
        assert finished == [1]
        queue.ensure_can_enqueue(uuid.uuid4(), held_bytes=queue._max_held_bytes)  # bytes released
        await queue.stop()

    asyncio.run(scenario())


def test_status_recording_errors_do_not_kill_the_worker():
    async def scenario():
        calls = []

        def flaky_recorder(analysis_id, status, error):
            calls.append(status)
            if len(calls) == 1:
                raise RuntimeError("database down")

        queue = JobQueue(flaky_recorder, workers=1)
        ran = []

        async def ok():
            ran.append(1)

        queue.start()
        queue.enqueue(_job(ok))
        queue.enqueue(_job(ok))
        await _wait_until(lambda: len(ran) == 2 and len(calls) == 4)
        await queue.stop()

    asyncio.run(scenario())
