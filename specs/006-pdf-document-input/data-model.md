# Data Model & Contract Changes: PDF Document Input

No database schema changes — `Analysis.filename` (`backend/db.py`) stays a plain `Text`
column; only the *value* written to it changes (see below). Everything else here is an
API contract change on the one existing endpoint.

## `POST /api/v1/compliance-check` — request changes

| Field | Before | After |
|---|---|---|
| `file` | required `UploadFile` (code file or `.zip`) | **optional** `UploadFile` |
| `pdf` | — | **new**, optional `UploadFile`, must have a `.pdf` extension |
| `company_name` | optional form field | unchanged |
| `company_context` | optional form field | unchanged |

**Validation** (in this order, before any processing):
1. If both `file` and `pdf` are absent → `400`, "at least one of a code file or a PDF is
   required" (FR-002).
2. If `pdf` is present but not a valid PDF (wrong extension, or `pypdf` fails to open it)
   → `400`, "invalid PDF" (FR-005) — same shape as today's "unsupported file
   format"/"invalid ZIP" errors.
3. Existing `file` validation (extension, size ceiling) unchanged when `file` is present.
4. `pdf` size ceiling: reuses `MAX_FILE_SIZE` (research.md).

## `POST /api/v1/compliance-check` — response changes

| Field | Before | After |
|---|---|---|
| `pdf_warning` | — | **new**, optional string. Present only when a meaningful share of the PDF's pages had no extractable text (FR-006a); absent (or `null`) otherwise, including when no PDF was submitted at all. |
| everything else | unchanged shape | unchanged shape |

`pdf_warning` wording follows the two cases from spec.md's Edge Cases:
- No PDF text extracted at all: "Aucun texte n'a pu être extrait du PDF (probablement un
  document scanné) ; son contenu n'a pas été pris en compte."
- Partial extraction (some pages unreadable): "N page(s) sur M du PDF n'ont pas pu être
  lues comme texte et n'ont pas été prises en compte."

## Changed entity: `Analysis.filename` (`backend/db.py`)

**Before**: always the uploaded code file's original filename.

**After**: reflects whichever source(s) were actually submitted —
- code only: unchanged (code filename).
- PDF only: the PDF's filename.
- both: both filenames joined for display (e.g. `"app.zip + register.pdf"`), so the
  history list (`specs/005-user-accounts-history`) still shows something meaningful
  without adding a new column for a second filename.

## Internal: `pdf_extract.py` output (not persisted, in-memory only)

- **Input**: raw PDF bytes, original filename (for the `## File:` header).
- **Output**: `(text: str, pages_with_text: int, total_pages: int)`.
  - `text` is empty (`""`) if no page yielded extractable text.
  - A page that raises during extraction counts as unreadable (not in
    `pages_with_text`), not a fatal error for the request (FR-006).
- Never written to disk or the database — same "content is never stored" handling as the
  code path (`main.py`'s existing `TemporaryDirectory` usage stores code only for the
  duration of one request; the PDF's bytes live only in the request handler's memory for
  the same duration).
