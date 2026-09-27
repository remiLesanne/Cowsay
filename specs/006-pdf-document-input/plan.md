# Implementation Plan: PDF Document Input for Compliance Checks

**Branch**: `feature/pdf-document-input` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-pdf-document-input/spec.md`

## Summary

Make the existing code file/zip upload on `/api/v1/compliance-check` optional, and add a
second optional PDF upload alongside it — at least one of the two must be present. A new
`pdf_extract.py` module extracts whatever text is present in the PDF's pages (skipping
image-only pages, no OCR) and formats it with the same `## File: <name> (page N)` header
convention Repomix's markdown output already uses. That means the existing chunker/index
in `code_index.py` needs **zero changes**: the Repomix representation and the extracted
PDF text are simply concatenated into one `code_context` string before being indexed, so
a question can be answered from either source (or both) exactly as it is today from code
alone. A warning is returned when a meaningful share of the PDF couldn't be read as text.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript/Next.js (frontend) — unchanged.

**Primary Dependencies**: `pypdf` (new) — pure-Python PDF text extraction, no system
package required (rules out poppler/tesseract-based approaches, which would grow the
Docker image the same way Playwright/Chromium already does, for a capability — OCR —
this feature explicitly excludes per spec.md FR-006). No new frontend dependency (a
second native `<input type="file" accept="application/pdf">`).

**Storage**: N/A beyond the existing `Analysis` row (spec 005) — a PDF's raw bytes are
never persisted, only its extracted text is used in-memory for the request, exactly like
code today (spec 005's "the code itself is never stored" principle extends unchanged).

**Testing**: manual, per this plan's `quickstart.md` (no automated suite yet — same
tracked gap as every prior spec in this repo, not introduced or fixed here).

**Target Platform**: same existing backend/frontend.

**Project Type**: web-service + web-app (existing structure).

**Performance Goals**: PDF text extraction must not become the new bottleneck now that
indexing itself was just sped up (fastembed switch, README Deployment section) — `pypdf`
extraction of a bounded-length document (tens of pages) is expected to take low
single-digit seconds, negligible next to embedding/LLM time.

**Constraints**: extraction must degrade per-page (skip what can't be read, keep what
can) rather than fail the whole request over one bad page (FR-006); must not add a system
package to the Docker image (Constitution Principle IV — deliberate, not accidental,
scope control).

**Scale/Scope**: a submitted PDF is one AI system's documentation (register entry, DPIA,
vendor factsheet) — a bounded document, not an arbitrarily large report (spec.md
Assumptions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (drive the real tool, never reimplement)**: N/A/PASS — this feature adds
  a new *source of facts* fed into the existing answering flow; it doesn't touch how the
  checker form itself is driven or interpreted.
- **Principle II (no silent guessing)**: PASS — a page whose text can't be extracted is
  excluded, never guessed at, and the user is explicitly warned when that happens (FR-006,
  FR-006a) instead of the system silently proceeding as if the whole document had been
  read.
- **Principle III (spec-driven development)**: PASS — this plan.
- **Principle IV (production-shaped, not a POC)**: PASS — `pypdf` was chosen specifically
  to avoid growing the Docker image/build surface with a system-level OCR dependency for a
  capability that isn't in scope; the PDF size ceiling is a deliberate, documented limit
  (spec.md Assumptions), not an arbitrary default.
- **Principle V (README stays current)**: README.md must document the new optional PDF
  input and the no-OCR/warning behavior once shipped — tracked as a task.

No violations — Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/006-pdf-document-input/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)

(no contracts/ subfolder — same reasoning as spec 003: one existing endpoint gains two
 optional fields and one optional response field; documenting that directly in
 data-model.md avoids duplicating it in a separate contracts file for a change this size)
```

### Source Code (repository root)

```text
backend/
├── main.py                  # POST /api/v1/compliance-check: `file` becomes optional,
│                             # + new optional `pdf: UploadFile` field; reject if both
│                             # are absent (FR-002); Repomix representation (if any) and
│                             # extracted PDF text (if any) are concatenated into one
│                             # `code_context` string before run_compliance_check;
│                             # fingerprint covers whichever source(s) were actually
│                             # given; response gains an optional `pdf_warning` string.
├── pdf_extract.py            # NEW: per-page text extraction from an uploaded PDF via
│                             # pypdf, formatted with the same "## File: <name>
│                             # (page N)" header convention Repomix's markdown output
│                             # already uses. Returns extracted text plus
│                             # (pages_with_text, total_pages) so main.py can build the
│                             # FR-006a warning. A page that raises during extraction is
│                             # treated as unreadable, not a fatal error for the request.
├── compliance_agent.py       # unchanged — already source-agnostic, it only ever sees
│                             # one combined `code_context` string
└── code_index.py             # unchanged — its chunker already keys off "## File:"
                              # headers regardless of where the text originated

frontend/
├── app/page.tsx              # + optional PDF file input alongside the existing code
│                             # file input; submit is blocked with a clear message if
│                             # neither is attached (FR-007)
└── app/lib/api.ts            # runComplianceCheck(...) gains an optional pdf param,
                              # sent as a second multipart field
```

**Structure Decision**: one new, narrowly-scoped backend module (`pdf_extract.py`),
matching this repo's existing one-module-per-concern pattern (`session_store.py`,
`auth.py`, `code_index.py`). Deliberately reusing Repomix's own `## File:` text
convention instead of inventing a parallel ingestion path means `code_index.py` and
`compliance_agent.py` need no changes at all — the per-question retrieval flow already
treats "the codebase" as one opaque text blob, so a second source concatenated into that
same blob is invisible to it by design.

## Complexity Tracking

No constitution violations — table not needed.
