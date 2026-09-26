import hashlib
import io
import logging
import subprocess
import sys
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import Response

load_dotenv()  # must run before compliance_agent reads MISTRAL_* at import time

import auth
import history
import session_store
from compliance_agent import run_compliance_check, run_compliance_check_with_index
from auth import get_current_user
from db import Analysis, User, get_db, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # creates users/analyses tables on first run (specs/005)
    yield


app = FastAPI(lifespan=lifespan)

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".php", ".rb", ".c", ".cpp", ".cs", ".xml", ".md",
    ".zip",
}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_ZIP_FILE_SIZE = 500 * 1024 * 1024
MAX_ARCHIVE_SIZE = 500 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
REPOMIX_TIMEOUT_SECONDS = 300
# On Windows, npm's extensionless ".bin/repomix" is a POSIX shell script that
# Windows can't execute directly (WinError 193) — the ".cmd" shim is the real
# entry point there. Linux/Docker (production) uses the extensionless script.
REPOMIX_BIN = Path(__file__).parent / "node_modules" / ".bin" / (
    "repomix.cmd" if sys.platform == "win32" else "repomix"
)
IGNORED_ARCHIVE_DIRECTORIES = {
    "node_modules",
    ".git",
    ".next",
    "dist",
    "build",
    "venv",
    "__pycache__",
}
REPOMIX_IGNORES = ",".join(
    f"{directory}/**" for directory in sorted(IGNORED_ARCHIVE_DIRECTORIES)
)

# 1. Le middleware CORS DOIT être ajouté en premier
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://cowsay-one.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Ensuite seulement, les routes
app.include_router(auth.router)
app.include_router(history.router)

@app.options("/")
def options_root():
    return Response(status_code=200)

@app.get("/")
def read_root():
    return {
        "message": "Cowsay backend API",
        "version": "1.0"
    }

def _is_ignored_archive_path(path: Path) -> bool:
    return any(
        directory in IGNORED_ARCHIVE_DIRECTORIES
        for directory in path.parts
    )


def _run_repomix(project_dir: Path, output_format: Literal["xml", "markdown"]):
    start = time.monotonic()
    try:
        completed_process = subprocess.run(
            [
                str(REPOMIX_BIN),
                "--style",
                output_format,
                "--output",
                "-",
                "--ignore",
                REPOMIX_IGNORES,
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=REPOMIX_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Repomix n’est pas installé sur le serveur",
        ) from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            status_code=504,
            detail="La conversion Repomix a dépassé le délai autorisé",
        ) from error

    if completed_process.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail="Repomix n’a pas réussi à convertir le projet",
        )

    logger.info("Repomix conversion took %.2fs", time.monotonic() - start)
    return completed_process.stdout


def _write_zip_to_project(archive: zipfile.ZipFile, project_dir: Path) -> list[str]:
    source_files = []
    uncompressed_size = 0

    for entry in archive.infolist():
        normalized_name = entry.filename.replace("\\", "/")
        entry_path = Path(normalized_name)

        if entry_path.is_absolute() or ".." in entry_path.parts:
            raise HTTPException(
                status_code=400,
                detail="L’archive contient un chemin de fichier dangereux",
            )

        if _is_ignored_archive_path(entry_path):
            continue

        if entry.is_dir():
            continue

        uncompressed_size += entry.file_size
        if uncompressed_size > MAX_ARCHIVE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Le contenu décompressé dépasse la limite autorisée",
            )

        if len(source_files) >= MAX_ARCHIVE_FILES:
            raise HTTPException(
                status_code=413,
                detail="L’archive contient trop de fichiers",
            )

        target = (project_dir / entry_path).resolve()
        if project_dir.resolve() not in target.parents:
            raise HTTPException(
                status_code=400,
                detail="L’archive contient un chemin de fichier dangereux",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(entry))

        if entry_path.suffix.lower() in ALLOWED_EXTENSIONS - {".zip"}:
            source_files.append(normalized_name)

    return source_files


def _fingerprint_project(project_dir: Path) -> str:
    # Content-based identity of the project (specs/005): hashes the extracted
    # files, not the upload, so the same code zipped twice (different zip
    # timestamps) gets the same fingerprint. Only this hash is stored, never
    # the code (FR-009).
    digest = hashlib.sha256()
    for path in sorted(p for p in project_dir.rglob("*") if p.is_file()):
        digest.update(path.relative_to(project_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


async def _convert_upload_to_repomix(
    file: UploadFile, output_format: Literal["xml", "markdown"]
) -> tuple[str, list[str], str, str]:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Format de fichier non pris en charge",
        )

    max_file_size = MAX_ZIP_FILE_SIZE if extension == ".zip" else MAX_FILE_SIZE
    content = await file.read(max_file_size + 1)

    if len(content) > max_file_size:
        raise HTTPException(
            status_code=413,
            detail=(
                "Archive ZIP trop volumineuse (500 Mo maximum)"
                if extension == ".zip"
                else "Fichier trop volumineux (10 Mo maximum)"
            ),
        )

    if not content:
        raise HTTPException(status_code=400, detail="Le fichier est vide")

    source_files = []
    with TemporaryDirectory(prefix="ai-risk-check-") as temporary_directory:
        project_dir = Path(temporary_directory) / "project"
        project_dir.mkdir()

        if extension == ".zip":
            try:
                archive = zipfile.ZipFile(io.BytesIO(content))
            except zipfile.BadZipFile as error:
                raise HTTPException(status_code=400, detail="Archive ZIP invalide") from error
            source_files = _write_zip_to_project(archive, project_dir)
        else:
            safe_filename = Path(filename).name or "uploaded-file"
            (project_dir / safe_filename).write_bytes(content)
            source_files = [safe_filename]

        fingerprint = _fingerprint_project(project_dir)
        representation = _run_repomix(project_dir, output_format)

    return representation, source_files, extension, fingerprint


@app.post("/api/v1/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    output_format: Literal["xml", "markdown"] = "xml",
):
    """Convert an uploaded project to an AI-friendly Repomix representation."""
    representation, source_files, extension, _ = await _convert_upload_to_repomix(file, output_format)

    return {
        "analysis_id": "temporary-id",
        "filename": file.filename or "",
        "status": "completed",
        "representation": representation,
        "representation_format": output_format,
        "summary": {
            "risk_level": "unknown",
            "score": 0,
        },
        "findings": [],
        "metadata": {
            "archive": extension == ".zip",
            "file_count": len(source_files),
            "files": source_files,
            "content_type": file.content_type,
        },
    }


def _index_unresolved(unresolved: list[dict]) -> dict[str, dict]:
    return {item["field_id"]: item for item in unresolved if "field_id" in item}


class AnswerItem(BaseModel):
    field_id: str
    value: str | list[str]


class AnswerRequest(BaseModel):
    answers: list[AnswerItem]


@app.post("/api/v1/compliance-check")
async def create_compliance_check(
    file: UploadFile = File(...),
    company_name: str | None = Form(default=None),
    company_context: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the uploaded project through the official EU AI Act Compliance Checker.

    Converts the project to a Repomix representation, then drives the checker
    at https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/
    with an LLM answering each question from the code (and optional company
    context), returning the checker's own recommendation.
    """
    representation, source_files, _, fingerprint = await _convert_upload_to_repomix(file, "markdown")

    extra_context = f"Company name: {company_name}\n{company_context or ''}".strip()
    result, project_index = await run_compliance_check(
        code_context=representation,
        system_name=company_name,
        extra_context=extra_context,
    )

    # Saved only once the check succeeded: a failed run raises above and leaves
    # nothing behind (spec 005 Edge Cases).
    analysis = Analysis(
        user_id=user.id,
        filename=file.filename or "",
        content_fingerprint=fingerprint,
        company_name=company_name or None,
        results_text=result["results_text"],
        is_complete=result["is_complete"],
        question_details=result["question_details"],
        needs_human_input=result["needs_human_input"],
    )
    db.add(analysis)
    db.commit()

    session_id = session_store.create_session(
        project_index, user.id, analysis.id, company_name, extra_context
    )
    session = session_store.get_session(session_id)
    session.unresolved_by_field_id = _index_unresolved(result["needs_human_input"])

    return {
        "session_id": session_id,
        "analysis_id": str(analysis.id),
        "filename": file.filename or "",
        "file_count": len(source_files),
        **result,
    }


@app.post("/api/v1/compliance-check/{session_id}/answer")
async def answer_compliance_check(
    session_id: str,
    body: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resume a compliance check with human-provided answers.

    Reuses the ProjectIndex built on the first call (no Repomix re-run, no
    re-embedding — see specs/003-human-in-loop-answers/research.md) and skips
    the LLM entirely for fields the human has now answered. Multiple-choice
    answers are validated against the question's real options before any
    browser automation runs, so a bad value fails fast instead of wasting a
    30-90s Playwright run.
    """
    session = session_store.get_session(session_id)
    # Someone else's session is reported exactly like an unknown one (FR-014).
    if session is None or session.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="Session inconnue ou expirée, merci de renvoyer le fichier",
        )

    accepted: dict[str, str | list[str]] = {}
    for answer in body.answers:
        unresolved = session.unresolved_by_field_id.get(answer.field_id)
        if unresolved is None:
            continue  # no longer part of the form — unused, not an error (spec 003)
        if unresolved["type"] not in ("radio", "checkbox"):
            # Free text has no option list to validate against, but must still be
            # applied — it used to be skipped here and silently lost (spec 005 FR-012).
            accepted[answer.field_id] = answer.value
            continue
        valid_options = {option.strip().lower() for option in unresolved["options"]}
        submitted = answer.value if isinstance(answer.value, list) else [answer.value]
        invalid = [value for value in submitted if value.strip().lower() not in valid_options]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Réponse invalide pour « {unresolved['question']} »",
                    "invalid_values": invalid,
                    "valid_options": unresolved["options"],
                },
            )
        accepted[answer.field_id] = answer.value
    # Stored only once the whole batch is valid, so a rejected request leaves
    # the session exactly as it was.
    session.human_answers.update(accepted)

    result = await run_compliance_check_with_index(
        session.project_index,
        system_name=session.system_name,
        extra_context=session.extra_context,
        human_answers=session.human_answers,
    )
    session.unresolved_by_field_id = _index_unresolved(result["needs_human_input"])

    analysis = db.get(Analysis, session.analysis_id)
    if analysis is not None and analysis.user_id == user.id:
        analysis.results_text = result["results_text"]
        analysis.is_complete = result["is_complete"]
        analysis.question_details = result["question_details"]
        analysis.needs_human_input = result["needs_human_input"]
        db.commit()

    return {
        "session_id": session_id,
        "analysis_id": str(session.analysis_id),
        "filename": analysis.filename if analysis else "",
        **result,
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
