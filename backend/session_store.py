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
    expires_at: float = 0.0


def _purge_expired() -> None:
    # get_session only drops the one expired entry it's asked about, so a session
    # nobody comes back to would otherwise hold its ProjectIndex (embeddings of the
    # whole project) in memory until the process restarts.
    now = time.time()
    for session_id in [sid for sid, session in _sessions.items() if session.expires_at < now]:
        del _sessions[session_id]


def create_session(
    project_index: ProjectIndex,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
    system_name: str | None,
    extra_context: str | None,
) -> str:
    _purge_expired()
    session_id = uuid.uuid4().hex
    _sessions[session_id] = ComplianceSession(
        project_index=project_index,
        user_id=user_id,
        analysis_id=analysis_id,
        system_name=system_name,
        extra_context=extra_context,
        expires_at=time.time() + SESSION_TTL_SECONDS,
    )
    return session_id


def get_session(session_id: str) -> ComplianceSession | None:
    session = _sessions.get(session_id)
    if session is None:
        return None
    if session.expires_at < time.time():
        del _sessions[session_id]
        return None
    session.expires_at = time.time() + SESSION_TTL_SECONDS
    return session


def find_session_id_by_analysis(analysis_id: uuid.UUID) -> str | None:
    """The live session for a saved analysis, if it hasn't expired — lets a
    reopened analysis still offer its pending questions (specs/005)."""
    _purge_expired()
    for session_id, session in _sessions.items():
        if session.analysis_id == analysis_id:
            return session_id
    return None
