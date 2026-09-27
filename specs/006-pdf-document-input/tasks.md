# Tasks: PDF Document Input for Compliance Checks

**Input**: Design documents from `specs/006-pdf-document-input/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested; manual validation via `quickstart.md` (same convention as every
prior spec in this repo).

**Organization**: by user story (US1 = PDF only, US2 = code only/regression, US3 = both
combined).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Add `pypdf` to `backend/requirements.txt` (research.md decision — pure-Python,
      no system package)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: PDF extraction and the now-optional-file endpoint contract both user stories
build on

- [X] T002 Created `backend/pdf_extract.py` (`extract_pdf_text`, `ExtractedPdf`,
      `InvalidPdfError`) exactly as specified. **Verified live** with real generated PDFs
      (reportlab, dev-only): a 3-page all-text PDF → `pages_with_text=3, total_pages=3`,
      correct `## File:` headers; a 2-page blank PDF → `pages_with_text=0`; a 3-page PDF
      with a blank middle page → `pages_with_text=2` with pages 1 and 3 correctly kept and
      correctly numbered (page 2 skipped, not renumbered); a non-PDF file → `InvalidPdfError`
      raised cleanly.
- [X] T003 `file` is now `UploadFile | None = File(default=None)`, `pdf` added as
      `UploadFile | None = File(default=None)`; the `file is None and pdf is None` check is
      the first line of `create_compliance_check`. **Verified live**: a request with neither
      field → `400` immediately (confirmed no Repomix/Playwright/LLM work started).

**Checkpoint**: the endpoint accepts an optional PDF and rejects an empty submission, but
nothing yet uses the PDF's content in the answering flow.

---

## Phase 3: User Story 1 - PDF only, no code (Priority: P1) 🎯 MVP

**Goal**: a user with only a PDF describing an AI system gets a real compliance-check
result, without needing any source code.

**Independent Test**: per `quickstart.md`'s "PDF only, no code" scenario.

### Implementation for User Story 1

- [X] T004 [US1] `_extract_pdf_upload` in `backend/main.py`: extension check, `MAX_FILE_SIZE`
      ceiling, `InvalidPdfError` → `400`. **Verified live**: a renamed non-PDF file → `400`.
- [X] T005 [US1] `representation = "\n\n".join(...)` combines Repomix output and PDF text.
      No changes made to `compliance_agent.py` or `code_index.py`, as planned. **Verified
      live** (real Mistral + Playwright run, PDF describing a fictional "Loan Approval
      Assistant" operated by "Acme Lending Corp", no code file): `Entity type` answered
      `Provider` with reasoning explicitly citing "Acme Lending Corp" from the PDF text —
      proves the PDF content reaches the LLM through the same retrieval path as code.
- [X] T006 [US1] Both `pdf_warning` wordings implemented in `_extract_pdf_upload`, included
      in the response only when non-empty. Also rendered in `frontend/app/analyse/page.tsx`
      as an amber banner (not originally its own task, but SC-005 requires the user to
      actually see it, not just have it in the API response). **Verified live**: a blank
      2-page PDF → `pdf_warning: "Aucun texte n'a pu être extrait du PDF..."`; a 3-page PDF
      with 1 blank page → `pdf_warning: "1 page(s) sur 3 du PDF n'ont pas pu être lues..."`
      (confirmed raw UTF-8 bytes are correct — an earlier mangled-looking display was a
      PowerShell/console artifact on the test client, not a server bug).
- [X] T007 [US1] `_combined_fingerprint(code_fingerprint, pdf_bytes)`: returns
      `code_fingerprint` unchanged when no PDF (byte-for-byte pre-feature behavior),
      otherwise folds the PDF's raw bytes into a new SHA-256 digest.
- [X] T008 [US1] `display_filename = " + ".join(...)` over whichever filename(s) were
      given. **Verified live**: PDF-only → `"register.pdf"`; combined → `"loan_model.py +
      combo_register.pdf"`.
- [X] T009 [US1] `runComplianceCheck(file, pdf, companyName?, companyContext?)` in
      `frontend/app/lib/api.ts`; `pdf` appended to `FormData` only when present.
- [X] T010 [US1] Second optional file input added in `frontend/app/page.tsx` (a compact
      "Choisir un PDF" control below the main drop zone, not a second full drag-and-drop
      zone — the PDF is the secondary/optional input), wired to `runComplianceCheck`.
- [X] T011 [US1] Submit button `disabled={(!file && !pdf) || isAnalysing}`, plus an inline
      message when both are empty (FR-007).

**Checkpoint**: a PDF-only submission produces a real result. Shippable increment (MVP).
**Verified**: `tsc --noEmit`, `next lint`, and `next build` all pass with no errors.
No browser-level visual check was done (no browser tool available in this environment) —
recommend a quick manual look before considering the UI itself (not just the API
contract) fully verified.

---

## Phase 4: User Story 2 - Code only, no PDF (Priority: P1 — regression)

**Goal**: the existing code-only flow behaves exactly as it did before this feature.

**Independent Test**: per `quickstart.md`'s "code only, no PDF" scenario.

### Implementation for User Story 2

- [X] T012 [US2] **Verified live**: a code-only submission (`loan_model.py`, no PDF)
      completed in 10.3s with `file_count: 1`, `filename: "loan_model.py"`, no
      `pdf_warning` key in the response, and `Entity type` correctly answered `Provider`
      citing "BetaCredit Systems" from the code — matches pre-feature shape and behavior.

**Checkpoint**: both PDF-only and code-only paths confirmed working independently.

---

## Phase 5: User Story 3 - PDF and code combined (Priority: P2)

**Goal**: when both a PDF and code are submitted, facts from either source are used.

**Independent Test**: per `quickstart.md`'s "both PDF and code" scenario.

### Implementation for User Story 3

- [X] T013 [US3] **Verified live**: `loan_model.py` (states `OPERATOR_NAME = "BetaCredit
      Systems"`, no mention of downstream modifications) submitted together with a PDF
      (states only "no downstream party has modified this system", no mention of the
      operator name). Result: `Entity type` → `Provider`, reasoning citing "BetaCredit
      Systems" (code-only fact); `Downstream modifications` → `None of the above` at
      **high** confidence, reasoning "The documentation explicitly states no downstream
      modifications were made" (PDF-only fact) — this exact question was **low-confidence/
      unresolved** in both the PDF-only and code-only runs above, and only got resolved
      once both sources were combined. This is the strongest possible evidence for SC-003:
      not just "both sources present", but a fact neither source alone could resolve.

**Checkpoint**: all three user stories independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T014 [P] **Verified live** (see T006): both the "nothing extractable" and "partial"
      `pdf_warning` scenarios ran end-to-end without failing, with the correct wording.
- [X] T015 [P] **Verified live** (see T003/T004): both fail fast with `400`, confirmed no
      Repomix/Playwright/LLM cost incurred for either.
- [X] T016 [P] **Verified live**: resumed a PDF-only session (built from a PDF with 1
      unreadable page) with a human answer for the still-unresolved "High-risk AI system:
      Annex I" question. The resume correctly applied the human answer
      (`source: "human"`), did **not** re-run Repomix or re-embed, and the real checker's
      branching logic revealed a genuinely new field (`wsf-1-field-wrapper-103`, "Annex I
      Section B") exactly as it would for a code-derived session — zero special-casing
      needed for a PDF-derived `ProjectIndex` in the resume path.
- [X] T017 Updated `README.md` (see commit) — architecture section, API docs, env vars,
      and Status section all now reflect the optional PDF input.

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
