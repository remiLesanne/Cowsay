import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

app = FastAPI()

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".php", ".rb", ".c", ".cpp", ".cs", ".xml", ".md",
    ".zip",
}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_ZIP_FILE_SIZE = 50 * 1024 * 1024
MAX_ARCHIVE_SIZE = 50 * 1024 * 1024
IGNORED_ARCHIVE_DIRECTORIES = {
    "node_modules",
    ".git",
    ".next",
    "dist",
    "build",
    "venv",
    "__pycache__",
}

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
        "message": "🔥 TEST DEPLOYMENT AWS - LE CORS ET LE CODE SONT BIEN A JOUR ! 🔥",
        "version": "v3-debug"
    }

@app.post("/api/v1/analyses")
async def create_analysis(file: UploadFile = File(...)):
    """Receive a source file and return a first analysis placeholder."""
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
                "Archive ZIP trop volumineuse (50 Mo maximum)"
                if extension == ".zip"
                else "Fichier trop volumineux (10 Mo maximum)"
            ),
        )

    if not content:
        raise HTTPException(status_code=400, detail="Le fichier est vide")

    if extension == ".zip":
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            archive_entries = archive.infolist()
        except zipfile.BadZipFile as error:
            raise HTTPException(status_code=400, detail="Archive ZIP invalide") from error

        source_files = []
        uncompressed_size = 0

        for entry in archive_entries:
            normalized_name = entry.filename.replace("\\", "/")
            entry_path = Path(normalized_name)

            if entry_path.is_absolute() or ".." in entry_path.parts:
                raise HTTPException(
                    status_code=400,
                    detail="L’archive contient un chemin de fichier dangereux",
                )

            if any(
                directory in IGNORED_ARCHIVE_DIRECTORIES
                for directory in entry_path.parts
            ):
                continue

            uncompressed_size += entry.file_size

            if entry.is_dir():
                continue

            if entry_path.suffix.lower() in ALLOWED_EXTENSIONS - {".zip"}:
                source_files.append(normalized_name)

        if uncompressed_size > MAX_ARCHIVE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Le contenu décompressé dépasse la limite autorisée",
            )

        return {
            "analysis_id": "temporary-id",
            "filename": filename,
            "status": "completed",
            "summary": {
                "risk_level": "unknown",
                "score": 0,
            },
            "findings": [],
            "metadata": {
                "archive": True,
                "file_count": len(source_files),
                "files": source_files,
                "uncompressed_size": uncompressed_size,
            },
        }

    decoded_content = content.decode("utf-8", errors="replace")

    return {
        "analysis_id": "temporary-id",
        "filename": filename,
        "status": "completed",
        "summary": {
            "risk_level": "unknown",
            "score": 0,
        },
        "findings": [],
        "metadata": {
            "content_length": len(decoded_content),
            "content_type": file.content_type,
        },
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
