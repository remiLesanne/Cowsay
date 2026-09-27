import time
import uuid
from dataclasses import dataclass, field

from code_index import ProjectIndex

SESSION_TTL_SECONDS = 30 * 60

# In-memory, single-process cache. Does not survive a restart/redeploy and
# does not scale beyond one instance — a deliberate trade-off documented in
# specs/003-human-in-loop-answers/research.md rather than a real database,
# since the only thing being cached is one ProjectIndex + accumulated answers
# for the lifetime of one user's compliance-check session.
_sessions: dict[str, "ComplianceSession"] = {}


@dataclass
class ComplianceSession:
    project_index: ProjectIndex
    # Owner and saved analysis (specs/005): a resume is refused for anyone else,
    # and updates this analysis row rather than creating a new one.
    user_id: uuid.UUID
    analysis_id: uuid.UUID
    system_name: str | None = None
    extra_context: str | None = None
    unresolved_by_field_id: dict[str, dict] = field(default_factory=dict)
    human_answers: dict[str, str | list[str]] = field(default_factory=dict)
    # The AI's answers already given in this analysis, by field id — reused on resume
    # instead of asking the LLM the same question again (specs/007 FR-010).
    ai_answers: dict[str, dict] = field(default_factory=dict)
    # True while a resume for it waits in the queue or runs: the 30-minute window
    # must not run out on a user who is only waiting their turn (specs/007 FR-009).
    busy: bool = False
    expires_at: float = 0.0


def _is_expired(session: ComplianceSession, now: float) -> bool:
    return not session.busy and session.expires_at < now


def _purge_expired() -> None:
    # get_session only drops the one expired entry it's asked about, so a session
    # nobody comes back to would otherwise hold its ProjectIndex (embeddings of the
    # whole project) in memory until the process restarts.
    now = time.time()
    for session_id in [sid for sid, session in _sessions.items() if _is_expired(session, now)]:
        del _sessions[session_id]


def create_session(
    project_index: ProjectIndex,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
    system_name: str | None,
    extra_context: str | None,
    ai_answers: dict[str, dict] | None = None,
) -> str:
    _purge_expired()
    session_id = uuid.uuid4().hex
    _sessions[session_id] = ComplianceSession(
        project_index=project_index,
        user_id=user_id,
        analysis_id=analysis_id,
        system_name=system_name,
        extra_context=extra_context,
        ai_answers=ai_answers if ai_answers is not None else {},
        expires_at=time.time() + SESSION_TTL_SECONDS,
    )
    return session_id


def get_session(session_id: str) -> ComplianceSession | None:
    session = _sessions.get(session_id)
    if session is None:
        return None
    if _is_expired(session, time.time()):
        del _sessions[session_id]
        return None
    session.expires_at = time.time() + SESSION_TTL_SECONDS
    return session


def mark_busy(session: ComplianceSession) -> None:
    session.busy = True


def release(session: ComplianceSession) -> None:
    """Ends a queued/running resume: the answering window restarts from now."""
    session.busy = False
    session.expires_at = time.time() + SESSION_TTL_SECONDS


def find_session_id_by_analysis(analysis_id: uuid.UUID) -> str | None:
    """The live session for a saved analysis, if it hasn't expired — lets a
    reopened analysis still offer its pending questions (specs/005)."""
    _purge_expired()
    for session_id, session in _sessions.items():
        if session.analysis_id == analysis_id:
            return session_id
    return None
