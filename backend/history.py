import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import ai_act
import session_store
from auth import get_current_user
from db import Analysis, ArticleExplanation, User, get_db

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

    return {
        "analysis_id": str(analysis.id),
        # Present only while the in-memory session is alive, so the UI knows whether
        # pending questions can still be answered in place (30 min, spec 003).
        "session_id": session_store.find_session_id_by_analysis(analysis.id),
        "filename": analysis.filename,
        "company_name": analysis.company_name,
        "content_fingerprint": analysis.content_fingerprint,
        "is_complete": analysis.is_complete,
        "results_text": analysis.results_text,
        "questions_answered": len(analysis.question_details),
        "question_details": analysis.question_details,
        "needs_human_input": analysis.needs_human_input,
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
    if cached is not None and cached.results_hash == results_hash:
        return cached.content

    content = await ai_act.explain(analysis.results_text, analysis.question_details)
    if any(article["available"] and not article["explanation"] for article in content["articles"]):
        # The LLM skipped an article: show what we have, but don't cache it, so the
        # next visit tries again instead of keeping a hole forever.
        return content
    # Upsert: two concurrent first loads (React dev mode fires effects twice) must not
    # collide on the primary key.
    statement = insert(ArticleExplanation).values(
        analysis_id=analysis.id, results_hash=results_hash, content=content
    )
    db.execute(statement.on_conflict_do_update(
        index_elements=[ArticleExplanation.analysis_id],
        set_={"results_hash": results_hash, "content": content},
    ))
    db.commit()
    return content
