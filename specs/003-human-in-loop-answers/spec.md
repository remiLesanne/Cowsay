# Feature Specification: Human-in-the-Loop Answers for Unresolved Questions

**Feature Branch**: `feature/human-in-the-loop-answers`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "when the AI can't answer confidently, it shouldn't waste
time, and the human should be able to submit an answer via the frontend; the frontend
should show the possible options, and the AI should ask again if the given answer isn't
one of the valid options."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Answer an unresolved question and get an updated result (Priority: P1)

A user runs a compliance check; the AI can't confidently answer one of the checker's
questions from the code alone (e.g. "Entity type" for a codebase with no clear AI
system). The frontend shows that question with its possible options. The user picks one
and submits. The check resumes and produces an updated (possibly still incomplete, but
further along) result — without re-uploading the file or re-running work already done.

**Why this priority**: This is the entire point of the feature — without it,
`needs_human_input` is just a diagnostic message with no way to act on it, and the user
is stuck re-running the whole check from scratch hoping to add more code/context.

**Independent Test**: Run a check on a project with no clear entity type (as observed
during manual testing), confirm `needs_human_input` includes the question's valid
options, submit one of them, confirm the resumed result no longer lists that question as
unresolved and reflects the chosen answer in the checker's actual state.

**Acceptance Scenarios**:

1. **Given** a completed check with one unresolved multiple-choice question, **When**
   the user submits one of the options shown, **Then** the resumed result answers that
   question with the submitted value and continues from there (may reveal new questions,
   may reach a final recommendation).
2. **Given** a resumed check that still has unresolved questions, **When** the user
   submits further answers, **Then** each round only requires the new answer(s) — not
   re-uploading the original file — since the project's code was already processed in
   round one.

---

### User Story 2 - Reject an answer that isn't a valid option (Priority: P1)

A user (or a non-UI API caller) submits an answer for a multiple-choice question that
isn't one of that question's valid options (typo, stale option list, direct API misuse).

**Why this priority**: Submitting the checker form with an invalid value would either be
silently ignored by the site (leaving the question effectively unanswered with no
explanation) or produce a nonsensical result — neither is acceptable for a compliance
tool whose output implies a legal recommendation.

**Independent Test**: Submit an answer string that doesn't match any of a question's
listed options; confirm the request is rejected with a clear error identifying which
question and which options were expected, and that no browser automation run was
wasted attempting it.

**Acceptance Scenarios**:

1. **Given** a question with options `["Provider", "Deployer", ...]`, **When** the user
   submits `"provider"` (wrong case) or `"Providerr"` (typo), **Then** the request is
   rejected before any browser automation runs, with the valid options listed again so
   the caller can correct it and resubmit.
2. **Given** a free-text (non-multiple-choice) unresolved question, **When** the user
   submits any non-empty text, **Then** it is accepted (no fixed option list to validate
   against).

### Edge Cases

- What happens if the user submits an answer for a question that's no longer part of the
  form (e.g. because an earlier answer changed made it disappear)? → The submitted
  answer for that question is simply unused; not an error (the form's own branching
  logic decides what's still relevant, per spec 001's Principle I — we drive the real
  tool, we don't second-guess its branching).
- What happens if the user never answers and just re-runs with a fresh upload instead?
  → Still works exactly as before this feature (spec 002 behavior unchanged) — this is
  an additional path, not a replacement for the original one-shot flow.
- What happens if too much time passes between round 1 and the human's answer (e.g. they
  leave the tab open overnight)? → The cached project data expires after a bounded time
  (see Assumptions); resuming after expiry requires re-uploading the file, with a clear
  error explaining why.
- What happens if the AI still can't confidently answer a *later* question even with the
  human's help on an earlier one? → That later question also appears in
  `needs_human_input` with its own options, following the same flow — this is inherently
  iterative, not resolved in one round necessarily.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST include, for each multiple-choice question in
  `needs_human_input`, the full list of valid options as the checker form presents them.
- **FR-002**: System MUST let a caller submit one or more human-provided answers for
  previously unresolved questions and resume the check using them, without requiring the
  original file to be re-uploaded.
- **FR-003**: System MUST validate a submitted multiple-choice answer against that
  question's actual valid options and reject the request (without running browser
  automation) if it doesn't match, returning the valid options again.
- **FR-004**: System MUST NOT re-ask the LLM for a question the human has already
  answered in a previous round — the human's answer is authoritative for that question.
- **FR-005**: System MUST continue to support the original one-shot flow (upload → full
  result, some of it possibly unresolved) unchanged for callers who don't use this
  feature.
- **FR-006**: Frontend MUST render each unresolved multiple-choice question with its
  options as selectable choices (not free text), so an invalid answer can't be typed in
  the first place for that question type; free-text unresolved questions keep a text
  input.
- **FR-007**: System MUST expire cached per-check data after a bounded time and give a
  clear, actionable error (not a silent failure) if a resume attempt arrives after
  expiry.

### Key Entities

- **Compliance check session**: server-side cache of one check's processed project
  data (chunked/indexed code) and the human answers accumulated so far, keyed by an
  opaque id returned from the first call. Expires after a bounded idle time (Assumptions).
- **Unresolved question** (extends `needs_human_input` from spec 001/002): now also
  carries `field_id`, `type` (`radio`/`checkbox`/`text`), and `options` (present only for
  `radio`/`checkbox`).
- **Human answer**: a `field_id` → value (string, or list of strings for checkbox)
  mapping submitted by the caller for a resume round.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from "one unresolved question" to "that question answered"
  without re-uploading their file.
- **SC-002**: An invalid multiple-choice answer is rejected before any browser
  automation starts (no wasted 30-90s run on a doomed request).
- **SC-003**: The frontend never lets a user type a free-text answer for a question that
  has a fixed option list.

## Assumptions

- Session cache is in-memory, single-process, with a fixed TTL (proposed: 30 minutes
  idle) — acceptable for this project's current single-instance deployment; would need
  a shared store (e.g. Redis) to survive a restart or scale beyond one instance, which
  is out of scope here (same category of trade-off as the 500MB indexing gap in
  `specs/002-rag-code-retrieval/research.md` — flagged, not solved).
- One HTTP round-trip per batch of human answers submitted; the frontend may batch
  multiple answered questions into one resume call if the user answers several at once
  before submitting.
- Resuming re-runs the Playwright browser session from scratch (spec 002's model — one
  browser session per HTTP request) but reuses the already-built code index instead of
  rebuilding it, and applies all accumulated human answers as soon as their fields
  become visible, rather than re-asking the LLM for them.
