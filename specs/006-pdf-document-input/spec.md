# Feature Specification: PDF Document Input for Compliance Checks

**Feature Branch**: `feature/pdf-document-input`

**Created**: 2026-09-27

**Status**: Implemented (2026-09-27) — all three user stories live-verified, including
the cross-source resolution proof for SC-003 (see `tasks.md`).

**Input**: User description: "Accept a PDF as an alternative or complementary input to
code for a compliance check. Sometimes the team only has a PDF describing the AI system
(e.g. an AI register entry / documentation), sometimes only source code, sometimes
possibly both. POST /api/v1/compliance-check should accept an optional PDF file in
addition to (or instead of) the existing code file/zip upload — at least one of the two
must be provided. Text extracted from the PDF should be available to the same
per-question answering flow as code excerpts, so questions can be answered from whichever
source(s) were actually supplied. Frontend upload UI needs to allow picking a PDF
alongside/instead of the code file."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a check from a PDF alone, with no source code (Priority: P1)

A user is assessing a third-party or legacy AI system for which they have no source code
— only its public documentation, such as an AI register entry (e.g. a city's public
register of the AI systems it uses). They upload just that PDF. The system answers the
checker's questions from the facts in the document, exactly as it would from code.

**Why this priority**: This is the case the feature exists for — without it, anyone
without source code (auditors, procurement reviewers, teams assessing a vendor's system)
simply cannot use this tool at all.

**Independent Test**: Submit a PDF describing a real AI system's purpose, users, and data
handling, with no code file. Confirm the check runs and produces answers grounded in the
PDF's content, with the same `needs_human_input` escalation for anything the document
doesn't cover.

**Acceptance Scenarios**:

1. **Given** no code file is provided, **When** a user submits only a PDF, **Then** the
   check runs using the PDF's extracted text as its only source and completes or escalates
   exactly as it would for a code-only submission.
2. **Given** a PDF whose text can be extracted, **When** a question is answered from it,
   **Then** the answer's reasoning/traceability reflects that the PDF was the source (same
   transparency the tool already gives for code-derived answers).

---

### User Story 2 - Run a check from code alone (Priority: P1)

A user has source code and no separate documentation PDF. This is today's existing flow
and must keep working unchanged now that a PDF is an option, not a requirement.

**Why this priority**: This is the tool's original, already-shipped use case; the feature
must not regress it.

**Independent Test**: Submit a code file/zip with no PDF, exactly as today. Confirm
behavior is identical to before this feature.

**Acceptance Scenarios**:

1. **Given** no PDF is provided, **When** a user submits only a code file/zip, **Then**
   the check behaves exactly as it did before this feature existed.

---

### User Story 3 - Combine a PDF and code for one check (Priority: P2)

A user has both source code and a documentation PDF (e.g. a register entry plus the
system's repository) and wants the check to use both — the PDF often states facts (who
operates the system, its stated purpose, who it affects) that aren't visible in code at
all, while the code shows technical implementation details the PDF omits.

**Why this priority**: Meaningfully improves answer quality/confidence over either source
alone, but the tool remains useful with just one source (P1s), so this is a valuable
addition rather than a blocker.

**Independent Test**: Submit both a code file and a PDF for the same system where each
source alone is missing a fact the other provides. Confirm a question answerable from
either source is answered, drawing on whichever source actually contains the relevant
fact.

**Acceptance Scenarios**:

1. **Given** both a PDF and a code file are submitted, **When** a question is answered
   from a fact that only appears in the PDF, **Then** it is answered correctly even though
   the code doesn't contain that fact (and symmetrically for a code-only fact).

---

### Edge Cases

- What happens when neither a code file nor a PDF is submitted? → Rejected before any
  processing starts, with a clear error stating that at least one is required (same
  "don't waste a run on a doomed request" principle as spec 003's invalid-answer
  rejection).
- What happens when a submitted PDF is not actually a PDF (wrong extension, corrupted
  file)? → Rejected with a clear error, matching how an unsupported code file extension
  is already rejected today.
- What happens when a PDF's text cannot be extracted at all (fully scanned/image-only
  document)? → No text is extracted, the user is warned that the PDF contributed nothing,
  and the check proceeds on whatever other source is available (code, if also supplied);
  if the PDF was the *only* source and none of its text was extractable, the check still
  runs but every question ends up escalated to `needs_human_input` — the same outcome as
  any source with no relevant content, not a special-cased failure.
- What happens when the PDF is mostly boilerplate/legal text with few facts relevant to
  the checker's questions? → No different from a code file with little relevant content
  today: the affected questions get low confidence and are escalated to
  `needs_human_input`, same as always — nothing new to build for this case.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept an optional PDF file on the compliance-check submission,
  alongside the existing optional code file/zip.
- **FR-002**: System MUST require at least one of {code file/zip, PDF} to be present, and
  reject the request before any processing (Repomix, browser automation, or LLM calls) if
  both are absent.
- **FR-003**: System MUST extract the text content of a submitted PDF and make it
  available to the same per-question answering flow that already serves code excerpts
  (chunked and retrieved per question, not just pasted once into every prompt) — including
  the existing "answer only from what the material supports, otherwise say so" instruction,
  applied identically to PDF-derived and code-derived facts.
- **FR-004**: System MUST support running a check from a PDF with no code file, from code
  with no PDF, or from both together, producing a result in the same shape
  (`results_text`, `question_details`, `needs_human_input`) regardless of which source(s)
  were used.
- **FR-005**: System MUST reject a file submitted in the PDF slot that isn't a valid PDF,
  with a clear error, without attempting to process it.
- **FR-006**: System MUST extract whatever text is present in the PDF's text layer, page
  by page, and MUST skip non-text content (images, scanned pages) without attempting OCR
  — text that can be extracted is used; content that can't is simply left out.
- **FR-006a**: System MUST warn the user when a meaningful portion of the PDF's content
  could not be extracted as text (e.g. because it consists of images or scanned pages),
  so they know that content wasn't considered — without blocking the check from
  proceeding (the check still runs on whatever text *was* extracted, same as any source
  with limited useful content).
- **FR-007**: Frontend upload UI MUST let a user attach a PDF, a code file/zip, or both, in
  one submission, and MUST block submission with a clear message if neither is attached.
- **FR-008**: System MUST continue to support the existing free-text company/system
  context field unchanged and independently of whether a PDF is also supplied (the two are
  additive, not exclusive).

### Key Entities

- **Submitted document (PDF)**: an optional second input file for one compliance check,
  parallel in role to the existing code file/zip — its extracted text becomes another
  source of retrievable facts for the same per-question answering flow. Not persisted as
  raw file bytes any more than code is today (spec 005's "the code itself is never
  stored" principle extends to the PDF).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with only a PDF (no source code) can obtain a complete or
  appropriately-escalated compliance check result.
- **SC-002**: A user with only source code continues to get identical results to before
  this feature, with zero behavior change.
- **SC-003**: When both a PDF and code are supplied, a fact stated in only one of the two
  is still answered correctly, showing both sources are actually consulted, not just one
  silently preferred.
- **SC-004**: Submitting neither a PDF nor a code file is rejected immediately, with no
  processing time wasted, and a message clear enough that the user knows to attach one.
- **SC-005**: A user who submits a scanned/image-only PDF (or one with some image-only
  pages) is clearly told that content wasn't usable as text, instead of silently getting
  a result that looks complete but was actually derived from little or no real content.

## Assumptions

- A submitted PDF describes one AI system's documentation (e.g. a register entry, a data
  protection impact assessment, a vendor factsheet) — a bounded-length document, not an
  arbitrarily large report; the existing per-file size ceiling used for a single code file
  is a reasonable starting limit for a PDF too, revisited only if real usage needs more.
- A PDF is provided in the same submission as any code file/zip for the same check — there
  is no separate "attach a PDF later" step during a human-in-the-loop resume round, mirroring
  how the code file itself can't be changed mid-resume today.
- The existing free-text company/system context field and a submitted PDF are both
  optional and independent; a user may use either, both, or neither (with code and/or PDF
  still governing whether the request is accepted at all per FR-002).
