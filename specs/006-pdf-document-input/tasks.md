# Tasks: PDF Document Input for Compliance Checks

**Input**: Design documents from `specs/006-pdf-document-input/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested; manual validation via `quickstart.md` (same convention as every
prior spec in this repo).

**Organization**: by user story (US1 = PDF only, US2 = code only/regression, US3 = both
combined).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Add `pypdf` to `backend/requirements.txt` (research.md decision — pure-Python,
      no system package)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: PDF extraction and the now-optional-file endpoint contract both user stories
build on

- [ ] T002 Create `backend/pdf_extract.py`: a function that takes raw PDF bytes + a
      filename, opens it with `pypdf.PdfReader`, and for each page calls
      `page.extract_text()`; a page whose extraction raises or returns empty/whitespace
      text is skipped (not a fatal error, per FR-006). Returns
      `(text: str, pages_with_text: int, total_pages: int)` where `text` joins each
      readable page as `## File: <filename> (page N)\n<page text>\n` (same header
      convention Repomix's markdown output uses, per research.md — this is what lets
      `code_index.py` stay unchanged). Raise a clear, catchable error (not import an
      unrelated pypdf exception type directly into `main.py`) if the file isn't openable
      as a PDF at all (FR-005).
- [ ] T003 In `backend/main.py`, change `create_compliance_check`'s `file` parameter from
      `UploadFile = File(...)` (required) to `UploadFile | None = File(default=None)`,
      and add `pdf: UploadFile | None = File(default=None)`. Add validation before any
      processing: if both `file` and `pdf` are `None`, raise `HTTPException(400, ...)`
      per data-model.md's request-changes table (FR-002) — this must be the very first
      check in the handler, before `_convert_upload_to_repomix` or `pdf_extract` are
      called.

**Checkpoint**: the endpoint accepts an optional PDF and rejects an empty submission, but
nothing yet uses the PDF's content in the answering flow.

---

## Phase 3: User Story 1 - PDF only, no code (Priority: P1) 🎯 MVP

**Goal**: a user with only a PDF describing an AI system gets a real compliance-check
result, without needing any source code.

**Independent Test**: per `quickstart.md`'s "PDF only, no code" scenario.

### Implementation for User Story 1

- [ ] T004 [US1] In `create_compliance_check` (`backend/main.py`), when `pdf` is present:
      read its bytes (reuse `MAX_FILE_SIZE` as the ceiling per research.md; same
      "trop volumineux" `413` wording style as the existing code-file check), validate
      the `.pdf` extension, call `pdf_extract`'s extraction function, and catch its
      "not a valid PDF" error into the same `400` shape used for an invalid ZIP (FR-005).
- [ ] T005 [US1] Build the combined `code_context` string: Repomix's `representation` (if
      `file` was given, else empty) concatenated with the PDF's extracted text (if `pdf`
      was given, else empty), joined with a blank line — pass this single string to
      `run_compliance_check` exactly as `representation` alone is passed today. No changes
      to `compliance_agent.py` or `code_index.py` (plan.md's core design decision).
- [ ] T006 [US1] Build the optional `pdf_warning` string per data-model.md's two wordings:
      when `pages_with_text == 0` (nothing extracted at all) vs. `0 < pages_with_text <
      total_pages` (partial). Omit the field entirely (or `None`) when no PDF was
      submitted, or when every page yielded text. Include it in the endpoint's response.
- [ ] T007 [US1] Update `_fingerprint_project`-based fingerprinting so it covers whichever
      source(s) were actually submitted: when only `pdf` is given (no `project_dir` from
      code), hash the PDF's raw bytes directly into the same SHA-256 digest instead of
      calling the code-only fingerprint helper; when both are given, extend one digest
      over both.
- [ ] T008 [US1] Set the saved `Analysis.filename` per data-model.md's rule: code
      filename when only `file` was given (unchanged), the PDF's filename when only `pdf`
      was given, or both joined (e.g. `"app.zip + register.pdf"`) when both were given.
- [ ] T009 [US1] In `frontend/app/lib/api.ts`, extend `runComplianceCheck`'s signature to
      accept an optional PDF `File` alongside the existing code file, appended to the
      `FormData` as a `pdf` field only when provided.
- [ ] T010 [US1] In `frontend/app/page.tsx`, add a second, optional file input
      (`accept="application/pdf"`) alongside the existing code upload, and pass it through
      to `runComplianceCheck`.
- [ ] T011 [US1] In `frontend/app/page.tsx`, block submission (with a clear inline
      message) when neither the code file nor the PDF input has a file selected (FR-007).

**Checkpoint**: a PDF-only submission produces a real result. Shippable increment (MVP).

---

## Phase 4: User Story 2 - Code only, no PDF (Priority: P1 — regression)

**Goal**: the existing code-only flow behaves exactly as it did before this feature.

**Independent Test**: per `quickstart.md`'s "code only, no PDF" scenario.

### Implementation for User Story 2

- [ ] T012 [US2] No new code expected — this story validates that Phase 2/3's changes
      (optional `file`, optional `pdf`, combined `code_context` build) produce byte-for-
      byte identical behavior when `pdf` is simply never provided. Run
      `quickstart.md`'s regression scenario and confirm the response, timing, and saved
      `Analysis` row all match pre-feature behavior.

**Checkpoint**: both PDF-only and code-only paths confirmed working independently.

---

## Phase 5: User Story 3 - PDF and code combined (Priority: P2)

**Goal**: when both a PDF and code are submitted, facts from either source are used.

**Independent Test**: per `quickstart.md`'s "both PDF and code" scenario.

### Implementation for User Story 3

- [ ] T013 [US3] No new code expected — the concatenation approach from T005 already
      combines both sources into one retrievable index by construction. Run
      `quickstart.md`'s combined scenario (a fact only in the PDF, a fact only in the
      code) and confirm both are answered correctly, proving both sources are actually
      consulted rather than one silently shadowing the other.

**Checkpoint**: all three user stories independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T014 [P] Run `quickstart.md`'s "PDF with no extractable text" and "PDF with some
      unreadable pages" scenarios — confirm `pdf_warning` wording and that the check still
      completes/escalates rather than failing outright (FR-006, FR-006a, SC-005).
- [ ] T015 [P] Run `quickstart.md`'s "invalid PDF upload" and "neither PDF nor code"
      scenarios — confirm both fail fast with a `400` and no wasted processing (SC-004).
- [ ] T016 [P] Run `quickstart.md`'s regression check against
      `specs/003-human-in-loop-answers` — resume a PDF-only or PDF+code session and
      confirm it behaves identically to a code-only session.
- [ ] T017 Update `README.md`: document the now-optional code upload, the new PDF input,
      the no-OCR/skip-and-warn behavior, and the `pdf_warning` response field (Constitution
      Principle V).

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** blocks all three user stories.
- **US1 (Phase 3)** is the MVP — the actual new capability (PDF-only checks).
- **US2 (Phase 4)** and **US3 (Phase 5)** are verification-only on top of US1's
  implementation (the combined-`code_context` design in T005 makes both "free" — this
  mirrors data-model.md's point that `code_index.py` treats one blob of text as one blob
  regardless of source), but each still gets its own checkpoint per spec.md's
  independent-test requirement.
- **Polish (Phase 6)** after all three stories are verified.

## Implementation Strategy

1. Setup + Foundational — endpoint accepts an optional PDF, rejects an empty submission.
2. US1 → the actual capability ships (PDF-only checks work end-to-end). MVP.
3. US2 → confirm zero regression for existing code-only users.
4. US3 → confirm combining both sources actually works, not just that neither path alone
   broke.
5. Polish → edge cases (unreadable PDFs, invalid uploads) + README.
