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
    system_name: str | None = None
    extra_context: str | None = None
    unresolved_by_field_id: dict[str, dict] = field(default_factory=dict)
    human_answers: dict[str, str | list[str]] = field(default_factory=dict)
    expires_at: float = 0.0


def create_session(
    project_index: ProjectIndex, system_name: str | None, extra_context: str | None
) -> str:
    session_id = uuid.uuid4().hex
    _sessions[session_id] = ComplianceSession(
        project_index=project_index,
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
