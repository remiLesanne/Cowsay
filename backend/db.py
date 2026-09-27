import os
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid, create_engine, func, text
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


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(Text)
    # SHA-256 of the extracted project files — never the code itself (spec FR-009).
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    results_text: Mapped[str] = mapped_column(Text)
    is_complete: Mapped[bool] = mapped_column(Boolean)
    question_details: Mapped[list] = mapped_column(JSONB, default=list)
    needs_human_input: Mapped[list] = mapped_column(JSONB, default=list)
    # specs/006: why part of a submitted PDF was ignored, so a reopened analysis
    # still tells the user its answers didn't use those pages.
    pdf_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS pdf_warning TEXT"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
