import io
import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

load_dotenv()  # must run before compliance_agent reads ZAI_* at import time

from compliance_agent import run_compliance_check

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
    result = await run_compliance_check(
        code_context=representation,
        system_name=company_name,
        extra_context=extra_context,
    )

    return {
        "filename": file.filename or "",
        "file_count": len(source_files),
        **result,
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
