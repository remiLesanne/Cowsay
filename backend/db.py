import os
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    create_engine,
    func,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# Local PostgreSQL today, a managed one (Supabase/Neon) once deployed — only this
# URL changes (specs/005-user-accounts-history/research.md). Must be loaded (main.py's
# load_dotenv) before this module is imported.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL n’est pas configurée (ex. postgresql+psycopg://user:pass@localhost:5432/cowsay)"
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Stored lower-cased and trimmed (auth.py normalizes before insert/lookup), so
    # the unique constraint is effectively case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

INTERRUPTED_BY_RESTART = "Analyse interrompue par un redémarrage du serveur — merci de la relancer."


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(Text)
    # SHA-256 of the extracted project files — never the code itself (spec FR-009).
    # Empty until the first run has extracted the files (specs/007: the row now
    # exists from submission time).
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True, default="")
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    results_text: Mapped[str] = mapped_column(Text, default="")
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    question_details: Mapped[list] = mapped_column(JSONB, default=list)
    needs_human_input: Mapped[list] = mapped_column(JSONB, default=list)
    # specs/006: why part of a submitted PDF was ignored, so a reopened analysis
    # still tells the user its answers didn't use those pages.
    pdf_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    # specs/007: queued -> running -> done | failed; a resume moves it back to queued.
    # Rows created before this column existed are finished analyses, hence 'done'.
    status: Mapped[str] = mapped_column(String(16), default=STATUS_DONE, server_default=STATUS_DONE)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def init_db() -> None:
    # create_all instead of migrations: two new tables, no existing data to migrate
    # (accepted trade-off, see research.md).
    Base.metadata.create_all(engine)
    # create_all never alters an existing table, so columns added after the first
    # deploy are added here, idempotently, until the project moves to migrations.
    with engine.begin() as connection:
        for statement in (
            "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS pdf_warning TEXT",
            "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'done'",
            "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS error TEXT",
            "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
        ):
            connection.execute(text(statement))


def recover_interrupted_analyses() -> int:
    """Fails every analysis a previous process left queued or running (specs/007 FR-015).

    The queue lives in memory and the uploaded material is never kept (spec 005), so
    these can't be continued — without this they would spin as "en cours" forever.
    """
    with SessionLocal() as db:
        result = db.execute(
            update(Analysis)
            .where(Analysis.status.in_(ACTIVE_STATUSES))
            .values(status=STATUS_FAILED, error=INTERRUPTED_BY_RESTART, finished_at=func.now())
        )
        db.commit()
        return result.rowcount


def record_analysis_status(analysis_id: uuid.UUID, status: str, error: str | None = None) -> None:
    with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            return  # the user's account (and its analyses) was deleted meanwhile
        analysis.status = status
        if status == STATUS_RUNNING:
            analysis.started_at = func.now()
            analysis.finished_at = None
            analysis.error = None
        elif status in (STATUS_DONE, STATUS_FAILED):
            analysis.finished_at = func.now()
            analysis.error = error
        db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
