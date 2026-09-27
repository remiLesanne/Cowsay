import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)


class InvalidPdfError(Exception):
    """Raised when the uploaded file can't be opened as a PDF at all."""


@dataclass
class ExtractedPdf:
    text: str
    pages_with_text: int
    total_pages: int


def extract_pdf_text(content: bytes, filename: str) -> ExtractedPdf:
    """Extracts whatever text is present in a PDF's pages.

    Pages with no text layer (scanned/image-only) are skipped, not OCR'd (spec
    006 FR-006 — no silent guessing at content that isn't actually there).
    Each readable page is formatted with the same "## File: <path>" header
    Repomix's markdown output already uses, so the existing chunker in
    code_index.py needs no changes at all to index this text alongside code.
    """
    try:
        reader = PdfReader(io.BytesIO(content))
        total_pages = len(reader.pages)
    except (PdfReadError, ValueError) as error:
        raise InvalidPdfError(str(error)) from error

    parts: list[str] = []
    pages_with_text = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            # A single unreadable page (corrupt content stream, unsupported
            # encoding) must not fail the whole document — it's simply treated
            # as if it had no text, same as a scanned page.
            logger.warning(
                "Could not extract text from page %d of %s", page_number, filename
            )
            continue

        if not text:
            continue

        pages_with_text += 1
        parts.append(f"## File: {filename} (page {page_number})\n{text}\n")

    return ExtractedPdf(
        text="\n".join(parts), pages_with_text=pages_with_text, total_pages=total_pages
    )
