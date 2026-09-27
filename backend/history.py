import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import ai_act
import session_store
from auth import get_current_user
from db import ACTIVE_STATUSES, STATUS_QUEUED, Analysis, ArticleExplanation, User, get_db
from job_queue import analysis_queue

router = APIRouter(prefix="/api/v1/history", tags=["history"])


@router.get("")
def list_analyses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analyses = db.scalars(
        select(Analysis).where(Analysis.user_id == user.id).order_by(Analysis.created_at.desc())
    )
    return [
        {
            "id": str(analysis.id),
            "filename": analysis.filename,
            "company_name": analysis.company_name,
            "is_complete": analysis.is_complete,
            "status": analysis.status,
            "created_at": analysis.created_at,
            "updated_at": analysis.updated_at,
        }
        for analysis in analyses
    ]


def _owned_analysis(analysis_id: uuid.UUID, user: User, db: Session) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    # Another user's analysis is reported exactly like a missing one (spec 005 FR-014).
    if analysis is None or analysis.user_id != user.id:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    return analysis


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    analysis = _owned_analysis(analysis_id, user, db)

    # Polled every few seconds while the analysis waits or runs (specs/008).
    position = analysis_queue.position(analysis.id) if analysis.status == STATUS_QUEUED else None
    return {
        "analysis_id": str(analysis.id),
        # Present only while the in-memory session is alive, so the UI knows whether
        # pending questions can still be answered in place (30 min, spec 003) — and
        # not while a run is queued/running, when there is nothing to answer yet.
        "session_id": (
            None
            if analysis.status in ACTIVE_STATUSES
            else session_store.find_session_id_by_analysis(analysis.id)
        ),
        "filename": analysis.filename,
        "company_name": analysis.company_name,
        "content_fingerprint": analysis.content_fingerprint,
        "status": analysis.status,
        "error": analysis.error,
        "queue_position": position,
        "estimated_wait_seconds": analysis_queue.estimate_seconds(position),
        "is_complete": analysis.is_complete,
        "results_text": analysis.results_text,
        "questions_answered": len(analysis.question_details),
        "question_details": analysis.question_details,
        "needs_human_input": analysis.needs_human_input,
        "pdf_warning": analysis.pdf_warning,
        "started_at": analysis.started_at,
        "finished_at": analysis.finished_at,
        "created_at": analysis.created_at,
        "updated_at": analysis.updated_at,
    }


@router.get("/{analysis_id}/articles")
async def get_article_explanations(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Explanations of the AI Act articles cited by the verdict (specs/007).

    Generated on the first call for a given verdict, then served from the database;
    a resume round that changes the verdict changes its hash and triggers a new set.
    """
    analysis = _owned_analysis(analysis_id, user, db)
    if not analysis.is_complete:
        # A non-final verdict isn't explained (spec 007 Edge Cases): no AI call, nothing stored.
        return {"status": "incomplete", "articles": [], "see_also": []}

    # Verdict + prompt version: a changed verdict or a changed prompt regenerates.
    results_hash = hashlib.sha256(f"v{ai_act.EXPLANATION_VERSION}\n{analysis.results_text}".encode()).hexdigest()
    cached = db.get(ArticleExplanation, analysis.id)
    if is_usable_cache(cached, results_hash, datetime.now(timezone.utc)):
        return cached.content

    content = await ai_act.explain(analysis.results_text, analysis.question_details)
    if any(article["available"] and not article["explanation"] for article in content["articles"]):
        # The LLM skipped an article: show what we have and retry later, not on every
        # page load — each try is a multi-thousand-token call on the shared quota.
        content = {**content, "partial": True}
    # Upsert: two concurrent first loads (React dev mode fires effects twice) must not
    # collide on the primary key. created_at is set explicitly: ON CONFLICT DO UPDATE
    # doesn't apply the column's onupdate, and the partial-retry delay counts from it.
    statement = insert(ArticleExplanation).values(
        analysis_id=analysis.id, results_hash=results_hash, content=content
    )
    db.execute(statement.on_conflict_do_update(
        index_elements=[ArticleExplanation.analysis_id],
        set_={"results_hash": results_hash, "content": content, "created_at": func.now()},
    ))
    db.commit()
    return content


# How long a set with a skipped article is served before generation is tried again.
PARTIAL_EXPLANATIONS_RETRY_AFTER = timedelta(minutes=10)


def is_usable_cache(cached: ArticleExplanation | None, results_hash: str, now: datetime) -> bool:
    if cached is None or cached.results_hash != results_hash:
        return False
    if not cached.content.get("partial"):
        return True
    return now - cached.created_at < PARTIAL_EXPLANATIONS_RETRY_AFTER
