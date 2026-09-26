import asyncio
import io
import json
import logging
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import Response

load_dotenv()  # must run before compliance_agent reads ZAI_* at import time

import session_store
from code_index import build_project_index
from compliance_agent import run_compliance_check, run_compliance_check_with_index
from project_summary import generate_project_summary

MAX_EXTRA_DOCUMENT_SIZE = 5 * 1024 * 1024

app = FastAPI()

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


async def _convert_upload_to_repomix(
    file: UploadFile, output_format: Literal["xml", "markdown"]
) -> tuple[str, list[str], str]:
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

        representation = _run_repomix(project_dir, output_format)

    return representation, source_files, extension


@app.post("/api/v1/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    output_format: Literal["xml", "markdown"] = "xml",
):
    """Convert an uploaded project to an AI-friendly Repomix representation."""
    representation, source_files, extension = await _convert_upload_to_repomix(file, output_format)

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


@app.post("/api/v1/compliance-check/analyze")
async def analyze_compliance_check(
    file: UploadFile = File(...),
    company_name: str | None = Form(default=None),
    company_context: str | None = Form(default=None),
):
    """specs/004-two-stage-analysis, step 1: understand the project.

    Converts the project to a Repomix representation, then asks an LLM for one
    coherent summary of the system plus an explicit list of information gaps —
    before any browser automation runs. See create_compliance_check for the
    older single-call flow this supersedes (kept for backward compatibility).
    """
    representation, source_files, _ = await _convert_upload_to_repomix(file, "markdown")
    extra_context = f"Company name: {company_name}\n{company_context or ''}".strip()

    project_index, summary = await asyncio.gather(
        asyncio.to_thread(build_project_index, representation),
        generate_project_summary(representation, extra_context),
    )

    session_id = session_store.create_session(
        project_index, company_name, extra_context, code_context=representation
    )
    session = session_store.get_session(session_id)
    session.summary = summary

    return {
        "session_id": session_id,
        "filename": file.filename or "",
        "file_count": len(source_files),
        **summary,
    }


@app.post("/api/v1/compliance-check/{session_id}/resolve-gaps")
async def resolve_gaps(
    session_id: str,
    answers: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
):
    """specs/004-two-stage-analysis, step 2: fill in what the summary is missing.

    `answers` is a JSON-encoded list of {"gap_id": "...", "text": "..."}. Either
    that or an extra `file` (read as plain text, not run through Repomix — a
    policy document, not necessarily code) is folded into the session's extra
    material and the summary is regenerated from scratch (code_context + all
    extra material so far), so it stays one coherent document rather than a
    patchwork of appended notes (see research.md).
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session inconnue ou expirée, merci de renvoyer le fichier",
        )

    if answers:
        try:
            parsed_answers = json.loads(answers)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=400, detail="Le champ answers n’est pas un JSON valide") from error
        for item in parsed_answers:
            session.extra_documents.append(
                f"Answer to gap '{item.get('gap_id', '')}': {item.get('text', '')}"
            )

    if file is not None:
        content = await file.read(MAX_EXTRA_DOCUMENT_SIZE + 1)
        if len(content) > MAX_EXTRA_DOCUMENT_SIZE:
            raise HTTPException(status_code=413, detail="Document trop volumineux (5 Mo maximum)")
        session.extra_documents.append(
            f"Uploaded document '{file.filename}':\n{content.decode('utf-8', errors='replace')}"
        )

    combined_code_context = "\n\n".join([session.code_context, *session.extra_documents])
    session.summary = await generate_project_summary(combined_code_context, session.extra_context or "")

    return {"session_id": session_id, **session.summary}


@app.post("/api/v1/compliance-check/{session_id}/run")
async def run_analyzed_compliance_check(session_id: str):
    """specs/004-two-stage-analysis, step 3: fill the form using the summary.

    Uses the session's current summary (post any gap resolution) as context
    instead of per-question code retrieval (spec 002) — see
    run_compliance_check_with_index's summary_context parameter.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session inconnue ou expirée, merci de renvoyer le fichier",
        )

    result = await run_compliance_check_with_index(
        session.project_index,
        system_name=session.system_name,
        extra_context=session.extra_context,
        summary_context=session.summary.get("summary", ""),
    )
    session.unresolved_by_field_id = _index_unresolved(result["needs_human_input"])

    return {"session_id": session_id, **result}


@app.post("/api/v1/compliance-check")
async def create_compliance_check(
    file: UploadFile = File(...),
    company_name: str | None = Form(default=None),
    company_context: str | None = Form(default=None),
):
    """Run the uploaded project through the official EU AI Act Compliance Checker.

    Converts the project to a Repomix representation, then drives the checker
    at https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/
    with an LLM answering each question from the code (and optional company
    context), returning the checker's own recommendation.
    """
    representation, source_files, _ = await _convert_upload_to_repomix(file, "markdown")

    extra_context = f"Company name: {company_name}\n{company_context or ''}".strip()
    result, project_index = await run_compliance_check(
        code_context=representation,
        system_name=company_name,
        extra_context=extra_context,
    )

    session_id = session_store.create_session(project_index, company_name, extra_context)
    session = session_store.get_session(session_id)
    session.unresolved_by_field_id = _index_unresolved(result["needs_human_input"])

    return {
        "session_id": session_id,
        "filename": file.filename or "",
        "file_count": len(source_files),
        **result,
    }


@app.post("/api/v1/compliance-check/{session_id}/answer")
async def answer_compliance_check(session_id: str, body: AnswerRequest):
    """Resume a compliance check with human-provided answers.

    Reuses the ProjectIndex built on the first call (no Repomix re-run, no
    re-embedding — see specs/003-human-in-loop-answers/research.md) and skips
    the LLM entirely for fields the human has now answered. Multiple-choice
    answers are validated against the question's real options before any
    browser automation runs, so a bad value fails fast instead of wasting a
    30-90s Playwright run.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session inconnue ou expirée, merci de renvoyer le fichier",
        )

    for answer in body.answers:
        unresolved = session.unresolved_by_field_id.get(answer.field_id)
        if unresolved is None or unresolved["type"] not in ("radio", "checkbox"):
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
        session.human_answers[answer.field_id] = answer.value

    result = await run_compliance_check_with_index(
        session.project_index,
        system_name=session.system_name,
        extra_context=session.extra_context,
        human_answers=session.human_answers,
    )
    session.unresolved_by_field_id = _index_unresolved(result["needs_human_input"])

    return {"session_id": session_id, **result}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
