import uuid
from datetime import datetime, timedelta, timezone

from db import ArticleExplanation
from history import PARTIAL_EXPLANATIONS_RETRY_AFTER, is_usable_cache

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _cached(content, age=timedelta(0), results_hash="h"):
    return ArticleExplanation(
        analysis_id=uuid.uuid4(), results_hash=results_hash, content=content, created_at=NOW - age
    )


def test_complete_explanations_are_served_from_cache_forever():
    assert is_usable_cache(_cached({"status": "ready"}, age=timedelta(days=30)), "h", NOW)


def test_a_changed_verdict_regenerates():
    assert not is_usable_cache(_cached({"status": "ready"}), "other-hash", NOW)
    assert not is_usable_cache(None, "h", NOW)


def test_partial_explanations_are_served_for_a_while_then_retried():
    partial = {"status": "ready", "partial": True}
    assert is_usable_cache(_cached(partial, age=timedelta(minutes=1)), "h", NOW)
    assert not is_usable_cache(_cached(partial, age=PARTIAL_EXPLANATIONS_RETRY_AFTER), "h", NOW)
