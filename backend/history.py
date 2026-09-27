import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import session_store
from auth import get_current_user
from db import Analysis, User, get_db

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


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    analysis = db.get(Analysis, analysis_id)
    # Another user's analysis is reported exactly like a missing one (spec 005 FR-014).
    if analysis is None or analysis.user_id != user.id:
        raise HTTPException(status_code=404, detail="Analyse introuvable")

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
        "pdf_warning": analysis.pdf_warning,
        "created_at": analysis.created_at,
        "updated_at": analysis.updated_at,
    }
