# Research: PDF Document Input for Compliance Checks

## Decision: PDF text extraction library — `pypdf`

**Decision**: use `pypdf` (the actively-maintained successor to PyPDF2), calling
`page.extract_text()` per page.

**Rationale**: pure-Python, no system package required — installs from a wheel exactly
like every other backend dependency in `requirements.txt` today. This matters because the
Dockerfile already carries one heavy native dependency (Playwright/Chromium, `apt-get
install`); adding a second one (e.g. `poppler-utils` for `pdf2image`, or a `tesseract-ocr`
system package for OCR) would grow build time and image size for a capability (page
rendering / OCR) this feature explicitly doesn't need, since FR-006 only requires
extracting text that's already present in the PDF's text layer.

**Alternatives considered**:
- `pdfplumber` (built on `pdfminer.six`): better layout-aware extraction (tables, columns)
  but heavier (pulls in `Pillow` and more transitive dependencies) for a benefit the use
  case doesn't need — the extracted text feeds an LLM prompt, not a structured-data
  pipeline, so exact layout fidelity isn't a requirement.
- `PyMuPDF` (`fitz`): fast and capable, but AGPL-licensed — a licensing constraint not
  worth taking on for this feature's scope when a permissively-licensed, pure-Python
  option (`pypdf`, BSD) does the job.
- OCR (`pytesseract` + `pdf2image`/`poppler-utils`, or a cloud OCR API): rejected per the
  spec.md clarification — out of scope, both for the system-dependency/image-size cost
  (local OCR) or external-API cost/dependency/another failure mode (cloud OCR), and for
  the correctness risk specific to a compliance tool: OCR misreads produce confidently
  wrong text fed straight to the LLM, which is a worse failure mode than the tool's
  existing "escalate to a human" path (Constitution Principle II).

## Decision: route PDF text through the existing Repomix-shaped chunker, unchanged

**Decision**: format extracted PDF text with the same `## File: <path>` header Repomix's
markdown output already uses (one per page: `## File: <pdf filename> (page N)`), then
concatenate it with the Repomix representation (if any) into a single `code_context`
string passed to the existing `build_project_index`/`chunk_repomix_output` in
`code_index.py`.

**Rationale**: `code_index.py`'s chunker is a plain regex split on that header — it has no
awareness of "code" as a concept beyond the text convention. Reusing it means the PDF's
per-question retrieval, chunk-size splitting, and low-confidence escalation behavior are
identical to code's, with zero new code in the retrieval/indexing layer and zero risk of
the two sources behaving inconsistently. This directly satisfies spec.md FR-003's
requirement that PDF text join "the same per-question answering flow" as code, not a
parallel one.

**Alternatives considered**:
- A second, PDF-specific `VectorIndexRetriever`/index, queried alongside the code one per
  question: rejected — doubles the indexing/retrieval code path for no behavioral benefit,
  and raises new questions (how to merge/rank results from two indexes) that the chosen
  approach avoids entirely by only ever building one index.
- Pasting the full PDF text into `extra_context` (sent with every question, unchunked):
  rejected — this is what `company_context` already does for short free text, but doesn't
  scale to a multi-page document and doesn't satisfy FR-003's explicit requirement to use
  the same chunked/retrieved flow as code.

## Decision: PDF size ceiling

**Decision**: reuse `MAX_FILE_SIZE` (10MB — today's single-code-file ceiling in
`main.py`) as the PDF ceiling too, rather than introducing a separate constant.

**Rationale**: spec.md's Assumptions already frame a submitted PDF as one bounded
document (a register entry, DPIA, or factsheet), the same order of magnitude as a single
source file, not a project archive — a 10MB PDF is already several hundred pages of pure
text, comfortably beyond what this use case needs. Reusing the existing constant avoids
introducing a second, undocumented number that could drift out of sync with the first.

**Alternatives considered**: a dedicated, smaller `MAX_PDF_FILE_SIZE` — rejected as
unnecessary precision for a limit that's already generous relative to the expected
document size; revisit only if real usage shows a need.
