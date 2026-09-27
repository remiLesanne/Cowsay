import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import session_store
from auth import get_current_user
from db import ACTIVE_STATUSES, STATUS_QUEUED, Analysis, User, get_db
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


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    analysis = db.get(Analysis, analysis_id)
    # Another user's analysis is reported exactly like a missing one (spec 005 FR-014).
    if analysis is None or analysis.user_id != user.id:
        raise HTTPException(status_code=404, detail="Analyse introuvable")

    # Polled every few seconds while the analysis waits or runs (specs/007).
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
