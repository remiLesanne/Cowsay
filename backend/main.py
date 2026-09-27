import asyncio
import hashlib
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, Literal

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
from auth import get_current_user
from compliance_agent import close_shared_browser, run_compliance_check, run_compliance_check_with_index
from db import (
    STATUS_QUEUED,
    Analysis,
    SessionLocal,
    User,
    get_db,
    init_db,
    recover_interrupted_analyses,
)
from job_queue import AlreadyQueued, Job, QueueFull, UserLimitReached, analysis_queue
from pdf_extract import InvalidPdfError, extract_pdf_text


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # creates users/analyses tables on first run (specs/005)
    # Uploads left by a previous process (killed without a clean shutdown) belong to
    # analyses that are about to be marked failed below: nothing will ever read them.
    shutil.rmtree(HELD_UPLOAD_DIR, ignore_errors=True)
    HELD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    recovered = recover_interrupted_analyses()
    if recovered:
        logger.warning("Marked %d analyses interrupted by the restart as failed", recovered)
    analysis_queue.start()
    yield
    await analysis_queue.stop()
    await close_shared_browser()


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
# Where uploads wait for their turn in the queue (specs/007 FR-018: temporary only).
HELD_UPLOAD_DIR = Path(tempfile.gettempdir()) / "cowsay-uploads"
# Guards only the Repomix-only /api/v1/analyses endpoint, which is still one
# synchronous request; compliance checks go through job_queue instead (specs/007).
MAX_CONCURRENT_REPOMIX_ONLY = 2
_repomix_only_slots = asyncio.Semaphore(MAX_CONCURRENT_REPOMIX_ONLY)
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

@asynccontextmanager
async def _repomix_only_slot():
    if _repomix_only_slots.locked():
        raise HTTPException(
            status_code=503,
            detail="Le serveur traite déjà le maximum de conversions simultanées, merci de réessayer dans quelques minutes",
        )
    async with _repomix_only_slots:
        yield


@contextmanager
def _queue_errors_as_http() -> Iterator[None]:
    try:
        yield
    except UserLimitReached as error:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Vous avez déjà {analysis_queue.max_per_user} analyses en cours ou en attente, "
                "merci d’attendre qu’une se termine"
            ),
        ) from error
    except QueueFull as error:
        raise HTTPException(
            status_code=503,
            detail="La plateforme est saturée, merci de réessayer dans quelques minutes",
        ) from error
    except AlreadyQueued as error:
        raise HTTPException(
            status_code=409,
            detail="Cette analyse est déjà en attente ou en cours, merci d’attendre son résultat",
        ) from error


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


def _checked_archive_entries(archive: zipfile.ZipFile) -> Iterator[tuple[zipfile.ZipInfo, Path, str]]:
    """Yields the archive's files to extract, enforcing every archive limit on the way.

    Works from the central directory only, so the same checks can run at submission
    time (nothing extracted — specs/007 FR-002) and again while extracting.
    """
    kept_files = 0
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

        # Counts every file written to disk, not just source files: an archive of
        # thousands of tiny non-source files is just as costly to extract and hash.
        if kept_files >= MAX_ARCHIVE_FILES:
            raise HTTPException(
                status_code=413,
                detail="L’archive contient trop de fichiers",
            )
        kept_files += 1

        yield entry, entry_path, normalized_name


def _open_zip(content: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise HTTPException(status_code=400, detail="Archive ZIP invalide") from error


def _validate_zip(content: bytes) -> None:
    for _ in _checked_archive_entries(_open_zip(content)):
        pass


def _write_zip_to_project(archive: zipfile.ZipFile, project_dir: Path) -> list[str]:
    source_files = []

    for entry, entry_path, normalized_name in _checked_archive_entries(archive):
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


def _combined_fingerprint(code_fingerprint: str, pdf_digest: str) -> str:
    # specs/006: extends spec 005's "content is never stored, only its hash is"
    # principle to a submitted PDF. Code-only and PDF-only stay identical to what
    # they were (the code fingerprint, or the PDF's own SHA-256); combining uses the
    # PDF's digest rather than its bytes so a queued job needn't keep the PDF around.
    if not pdf_digest:
        return code_fingerprint
    if not code_fingerprint:
        return pdf_digest
    return hashlib.sha256(f"{code_fingerprint}\0{pdf_digest}".encode()).hexdigest()


async def _extract_pdf_upload(pdf: UploadFile) -> tuple[bytes, str, str | None]:
    """Validates and extracts text from an uploaded PDF (specs/006).

    Returns (raw_bytes, extracted_text, warning) — warning is None unless a
    meaningful share of the PDF's pages had no extractable text (FR-006a).
    """
    filename = pdf.filename or ""
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Le fichier PDF doit avoir l’extension .pdf")

    content = await pdf.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="PDF trop volumineux (10 Mo maximum)")
    if not content:
        raise HTTPException(status_code=400, detail="Le PDF est vide")

    try:
        extracted = await asyncio.to_thread(extract_pdf_text, content, filename)
    except InvalidPdfError as error:
        raise HTTPException(status_code=400, detail="PDF invalide") from error

    warning = None
    if extracted.total_pages > 0 and extracted.pages_with_text == 0:
        warning = (
            "Aucun texte n’a pu être extrait du PDF (probablement un document scanné) ; "
            "son contenu n’a pas été pris en compte."
        )
    elif extracted.pages_with_text < extracted.total_pages:
        unreadable = extracted.total_pages - extracted.pages_with_text
        warning = (
            f"{unreadable} page(s) sur {extracted.total_pages} du PDF n’ont pas pu être "
            "lues comme texte et n’ont pas été prises en compte."
        )

    return content, extracted.text, warning


async def _read_code_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """Checks extension and size and reads the upload; returns (content, filename, extension)."""
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

    return content, filename, extension


def _prepare_project(
    content: bytes, filename: str, extension: str, output_format: Literal["xml", "markdown"]
) -> tuple[str, list[str], str]:
    source_files = []
    with TemporaryDirectory(prefix="ai-risk-check-") as temporary_directory:
        project_dir = Path(temporary_directory) / "project"
        project_dir.mkdir()

        if extension == ".zip":
            source_files = _write_zip_to_project(_open_zip(content), project_dir)
        else:
            safe_filename = Path(filename).name or "uploaded-file"
            (project_dir / safe_filename).write_bytes(content)
            source_files = [safe_filename]

        fingerprint = _fingerprint_project(project_dir)
        representation = _run_repomix(project_dir, output_format)

    return representation, source_files, fingerprint


# Login required: it accepts the same 500 MB uploads and runs the same Repomix
# subprocess as /compliance-check, so leaving it public was an open door to
# exhausting the server's CPU/disk without an account.
@app.post("/api/v1/analyses", dependencies=[Depends(get_current_user)])
async def create_analysis(
    file: UploadFile = File(...),
    output_format: Literal["xml", "markdown"] = "xml",
):
    """Convert an uploaded project to an AI-friendly Repomix representation."""
    async with _repomix_only_slot():
        content, filename, extension = await _read_code_upload(file)
        # Extraction, hashing and the Repomix subprocess are all blocking; run in a
        # worker thread so they don't freeze every other request (incl. /health).
        representation, source_files, _ = await asyncio.to_thread(
            _prepare_project, content, filename, extension, output_format
        )

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


@dataclass
class HeldUpload:
    """A code upload waiting in the queue: a private temp file, deleted by the queue
    once its job ends (specs/007 FR-018 — never stored durably)."""

    path: Path
    filename: str
    extension: str
    size: int


def _hold_upload(content: bytes, filename: str, extension: str) -> HeldUpload:
    HELD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="upload-", suffix=extension, dir=HELD_UPLOAD_DIR)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
    return HeldUpload(Path(path), filename, extension, len(content))


def _save_results(analysis_id: uuid.UUID, result: dict, fingerprint: str | None = None) -> None:
    logger.info(
        "Analysis %s run finished: %d questions answered, %d asked to the LLM",
        analysis_id, result["questions_answered"], result["llm_calls"],
    )
    with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            return  # the account (and its analyses) was deleted while this ran
        analysis.results_text = result["results_text"]
        analysis.is_complete = result["is_complete"]
        analysis.question_details = result["question_details"]
        analysis.needs_human_input = result["needs_human_input"]
        if fingerprint is not None:
            analysis.content_fingerprint = fingerprint
        db.commit()


async def _run_first_check(
    analysis_id: uuid.UUID,
    user_id: uuid.UUID,
    upload: HeldUpload | None,
    pdf_text: str,
    pdf_digest: str,
    company_name: str | None,
    extra_context: str,
) -> None:
    """Job body of a new analysis: everything that used to happen inside the request."""
    code_representation = ""
    code_fingerprint = ""
    if upload is not None:
        content = await asyncio.to_thread(upload.path.read_bytes)
        code_representation, _, code_fingerprint = await asyncio.to_thread(
            _prepare_project, content, upload.filename, upload.extension, "markdown"
        )

    # Both sources become one opaque text blob for the existing chunker/index
    # (code_index.py's "## File:" header convention already covers both — see
    # specs/006-pdf-document-input/plan.md) — no change needed there at all.
    representation = "\n\n".join(part for part in (code_representation, pdf_text) if part)
    ai_answers: dict[str, dict] = {}
    result, project_index = await run_compliance_check(
        code_context=representation,
        system_name=company_name,
        extra_context=extra_context,
        ai_answers=ai_answers,
    )
    _save_results(analysis_id, result, _combined_fingerprint(code_fingerprint, pdf_digest))

    session_id = session_store.create_session(
        project_index, user_id, analysis_id, company_name, extra_context, ai_answers
    )
    session_store.get_session(session_id).unresolved_by_field_id = _index_unresolved(
        result["needs_human_input"]
    )


async def _run_resume(session: session_store.ComplianceSession) -> None:
    """Job body of a resume: reuses the cached index, the human answers and the AI's
    earlier answers (no Repomix re-run, no re-embedding, no repeated LLM question)."""
    result = await run_compliance_check_with_index(
        session.project_index,
        system_name=session.system_name,
        extra_context=session.extra_context,
        human_answers=session.human_answers,
        ai_answers=session.ai_answers,
    )
    session.unresolved_by_field_id = _index_unresolved(result["needs_human_input"])
    _save_results(session.analysis_id, result)


def _accepted_response(analysis: Analysis, position: int, **extra) -> dict:
    return {
        "analysis_id": str(analysis.id),
        "status": STATUS_QUEUED,
        "queue_position": position,
        "estimated_wait_seconds": analysis_queue.estimate_seconds(position),
        "filename": analysis.filename,
        **extra,
    }


class AnswerItem(BaseModel):
    field_id: str
    value: str | list[str]


class AnswerRequest(BaseModel):
    answers: list[AnswerItem]


@app.post("/api/v1/compliance-check", status_code=202)
async def create_compliance_check(
    file: UploadFile | None = File(default=None),
    pdf: UploadFile | None = File(default=None),
    company_name: str | None = Form(default=None),
    company_context: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue the uploaded project for the official EU AI Act Compliance Checker.

    Validates the input, then returns 202 at once (specs/007): the check itself —
    Repomix on the code, text extracted from an optional PDF (specs/006), an LLM
    answering each question of
    https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/
    from whichever source(s) were supplied — runs from the queue, and its status and
    result are read from GET /api/v1/history/{analysis_id}. At least one of `file` or
    `pdf` is required.
    """
    if file is None and pdf is None:
        raise HTTPException(
            status_code=400,
            detail="Merci de fournir au moins un fichier de code ou un PDF",
        )
    with _queue_errors_as_http():
        # Fail fast, before reading a possibly large upload.
        analysis_queue.ensure_can_enqueue(user.id)

    # Every check that can fail on the input runs here, so the queue never holds a
    # request that is bound to fail (spec FR-002).
    code: tuple[bytes, str, str] | None = None
    if file is not None:
        code = await _read_code_upload(file)
        if code[2] == ".zip":
            await asyncio.to_thread(_validate_zip, code[0])

    pdf_text = ""
    pdf_warning: str | None = None
    pdf_digest = ""
    if pdf is not None:
        pdf_bytes, pdf_text, pdf_warning = await _extract_pdf_upload(pdf)
        pdf_digest = hashlib.sha256(pdf_bytes).hexdigest()

    upload = await asyncio.to_thread(_hold_upload, *code) if code is not None else None
    try:
        with _queue_errors_as_http():
            # Re-checked now that the upload's size is known; nothing below awaits,
            # so the check and the enqueue can't be separated by another request.
            analysis_queue.ensure_can_enqueue(user.id, upload.size if upload else 0)
    except HTTPException:
        if upload is not None:
            upload.path.unlink(missing_ok=True)
        raise

    filenames = [name for name in ((file.filename if file else ""), (pdf.filename if pdf else "")) if name]
    analysis = Analysis(
        user_id=user.id,
        filename=" + ".join(filenames),
        company_name=company_name or None,
        pdf_warning=pdf_warning,
        status=STATUS_QUEUED,
    )
    db.add(analysis)
    db.commit()

    extra_context = f"Company name: {company_name}\n{company_context or ''}".strip()
    position = analysis_queue.enqueue(Job(
        analysis_id=analysis.id,
        user_id=user.id,
        run=lambda: _run_first_check(
            analysis.id, user.id, upload, pdf_text, pdf_digest, company_name, extra_context
        ),
        held_file=upload.path if upload else None,
        held_bytes=upload.size if upload else 0,
    ))

    response = _accepted_response(analysis, position)
    if pdf_warning:
        response["pdf_warning"] = pdf_warning
    return response


@app.post("/api/v1/compliance-check/{session_id}/answer", status_code=202)
async def answer_compliance_check(
    session_id: str,
    body: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue a resume of a compliance check with human-provided answers.

    Reuses the ProjectIndex built on the first run (no Repomix re-run, no
    re-embedding — see specs/003-human-in-loop-answers/research.md), skips the LLM
    for fields the human has now answered and for those the AI already answered
    (specs/007). Multiple-choice answers are validated against the question's real
    options before anything is queued, so a bad value fails fast.
    """
    session = session_store.get_session(session_id)
    # Someone else's session is reported exactly like an unknown one (FR-014).
    if session is None or session.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="Session inconnue ou expirée, merci de renvoyer le fichier",
        )
    analysis = db.get(Analysis, session.analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable")

    with _queue_errors_as_http():
        if analysis_queue.is_active(session.analysis_id):
            raise AlreadyQueued
        analysis_queue.ensure_can_enqueue(user.id)

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

    analysis.status = STATUS_QUEUED
    analysis.error = None
    db.commit()
    session_store.mark_busy(session)
    position = analysis_queue.enqueue(Job(
        analysis_id=analysis.id,
        user_id=user.id,
        run=lambda: _run_resume(session),
        on_finish=lambda: session_store.release(session),
    ))

    response = _accepted_response(analysis, position, session_id=session_id)
    # Kept across resume rounds: the PDF pages that couldn't be read are still
    # missing from the answers, so the warning stays relevant.
    if analysis.pdf_warning:
        response["pdf_warning"] = analysis.pdf_warning
    return response


@app.get("/health")
def health_check():
    return {"status": "healthy"}
