import uuid

import session_store


def _new_session(analysis_id: uuid.UUID) -> str:
    return session_store.create_session(None, uuid.uuid4(), analysis_id, None, None)


def test_expired_sessions_are_purged_without_being_looked_up(monkeypatch):
    monkeypatch.setattr(session_store, "_sessions", {})
    stale_id = _new_session(uuid.uuid4())
    session_store._sessions[stale_id].expires_at = 0

    _new_session(uuid.uuid4())

    assert stale_id not in session_store._sessions
    assert len(session_store._sessions) == 1


def test_expired_session_is_not_found_by_analysis(monkeypatch):
    monkeypatch.setattr(session_store, "_sessions", {})
    analysis_id = uuid.uuid4()
    session_id = _new_session(analysis_id)
    assert session_store.find_session_id_by_analysis(analysis_id) == session_id

    session_store._sessions[session_id].expires_at = 0
    assert session_store.find_session_id_by_analysis(analysis_id) is None
    assert session_id not in session_store._sessions
