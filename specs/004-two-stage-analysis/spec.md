# Feature Specification: Two-Stage Analysis — Understand, Then Fill

**Feature Branch**: `feature/two-stage-analysis`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "First give the whole project to a first LLM that produces
a summary of what it understood the project does, listing all information that might be
needed to fill the form, and stating what kind of questions the code doesn't answer.
Give that summary to the AI that fills the form. That AI first looks for the info it
won't be able to answer and sends it to the user (so they either upload another document
with that info, or just answer directly), checks whether it now has it, then fills every
other question it can answer without a human."

## Why this replaces specs 002's per-question retrieval

Spec 002 answers each checker question by retrieving the top-k code chunks most similar
to that question's text (embeddings-based search) and feeding those to the LLM cold, one
question at a time, with no shared understanding of the project as a whole. This has two
weaknesses this feature addresses: (1) embedding similarity can miss code that's
genuinely relevant but phrased very differently from the question, and (2) the AI never
gets a coherent picture of the system — it reasons about each question in isolation. A
single upfront "understand the whole project" pass fixes both: one coherent summary,
written specifically to cover what the checker's questions tend to ask about, replaces
per-question retrieval as the context for every subsequent answer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a project understanding summary with explicit gaps (Priority: P1)

A user uploads their project. Before any form-filling happens, the system produces a
written summary of what the system does (purpose, data handled, deployment context,
users, etc. — whatever is relevant to AI Act questions) and an explicit list of
information categories the code doesn't cover.

**Why this priority**: Everything else in this feature depends on having this summary;
it's also independently useful as a sanity check the AI understood the project (per the
original project brief: "give a summary of the verification").

**Independent Test**: Upload a project with an obviously incomplete picture (e.g. code
with no mention of company location or EU market activity); confirm the summary
correctly describes what the code does AND explicitly lists "company location" /
"EU market activity" (or equivalent) as gaps, not just answering some checker questions
with unexplained low confidence.

**Acceptance Scenarios**:

1. **Given** a project whose code clearly implies its purpose (e.g. a facial-recognition
   function), **When** the summary is generated, **Then** it states that purpose
   correctly and does not list it as a gap.
2. **Given** a project with no information about company/deployment context, **When**
   the summary is generated, **Then** it explicitly names that category as a gap rather
   than silently omitting it.

---

### User Story 2 - Resolve gaps before the form-filling run starts (Priority: P1)

The user sees the identified gaps and, for each one, either types an answer directly or
uploads an additional document that might cover it — before the browser automation
against the official checker ever runs.

**Why this priority**: This is the actual behavior change requested — surfacing what's
missing *before* spending a full form-filling run, instead of discovering it reactively
mid-run (spec 003's flow) or not at all (spec 002 alone).

**Independent Test**: Upload a project with one clear gap; supply an answer for it;
confirm the form-filling run that follows uses that answer (the corresponding checker
question is answered correctly, not flagged as needing human input again).

**Acceptance Scenarios**:

1. **Given** an identified gap, **When** the user types a direct answer for it, **Then**
   that answer is available to the form-filling stage as if it had been in the code.
2. **Given** an identified gap, **When** the user uploads an additional document instead
   of typing an answer, **Then** the summary is regenerated including that document's
   content, and the gap is re-checked (it may now be resolved, or still be a gap if the
   document didn't actually cover it).
3. **Given** a user who chooses not to resolve a gap and proceeds anyway, **When** the
   form-filling run reaches a checker question that needed that missing information,
   **Then** it falls back to spec 003's existing per-question `needs_human_input` /
   resume flow — this feature narrows what ends up there, it doesn't replace that
   safety net.

---

### User Story 3 - Answerable questions get filled without human involvement (Priority: P2)

For every checker question the summary already covers, the form-filling stage answers it
automatically — the human is only asked about the gaps identified in User Story 1, not
about everything.

**Why this priority**: Without this, the feature would just move all the questions to
the human instead of the ones that genuinely need them.

**Independent Test**: Upload a project with a clear, unambiguous purpose and full
context (a "known-good" test project); confirm the resulting run reaches a final
recommendation with an empty (or near-empty) `needs_human_input`, same as before.

**Acceptance Scenarios**:

1. **Given** a project the summary describes confidently and completely, **When** the
   form-filling run happens, **Then** no gap-resolution round-trip is needed and the
   result is a normal completed (or reactively-fallback-flagged, per US2 scenario 3)
   check, matching spec 002/003 behavior for such a project today.

### Edge Cases

- What happens for a project too large for one summarization call? → Same category of
  problem spec 002's research.md already flagged for retrieval at scale; this feature
  doesn't need to solve it further, but the summarization step MUST NOT silently
  truncate without saying so — if the project has to be chunked/map-reduced to
  summarize, the final summary is still one coherent document (see Assumptions).
- What happens if the user uploads an additional document that's irrelevant or garbage?
  → The gap simply isn't resolved (per US2 Scenario 2, "still be a gap") — this is not
  an error case, it's the system correctly reporting it doesn't have the information.
- What happens if the summarization step itself is wrong (hallucinates purpose)? → Not
  fully solvable by this feature alone, but the requirement that the summary is shown
  to the user before form-filling proceeds (not just consumed invisibly) gives a human
  a chance to notice and correct it via the same gap-answering mechanism.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate one coherent project summary per compliance check,
  covering what the checker's questions tend to need (system purpose, data/subjects
  involved, deployment/market context, etc.), before any browser automation runs.
- **FR-002**: System MUST produce, alongside the summary, an explicit list of
  information-category gaps — things the summary could not determine from the code.
- **FR-003**: System MUST let the user resolve a gap either by typing a direct answer or
  by uploading an additional document, and MUST regenerate/update the summary to
  incorporate a newly uploaded document.
- **FR-004**: System MUST let the user proceed to form-filling without resolving every
  gap; unresolved gaps are not a hard blocker.
- **FR-005**: The form-filling stage MUST use the project summary (plus any resolved
  gap answers) as its context for answering checker questions, instead of per-question
  code retrieval.
- **FR-006**: System MUST still fall back to spec 003's existing per-question
  `needs_human_input` / resume mechanism for any checker question the summary-based
  context doesn't resolve, even after gap resolution (US2 Scenario 3) — this feature
  narrows that safety net's usage, it does not remove it.
- **FR-007**: System MUST NOT silently guess an answer for a gap it identified as
  missing — same non-negotiable principle as specs 001-003 (constitution Principle II).

### Key Entities

- **ProjectSummary**: the coherent, human-readable description of the project generated
  by the first LLM pass. Regenerated (not merely appended to) whenever new source
  material (an additional document) is added, so it stays one coherent document rather
  than a patchwork.
- **InformationGap**: one identified category of missing information, with enough
  description that a human knows what's being asked for (not just "unknown", but e.g.
  "no indication of which EU member state(s) the system operates in").
- **GapResolution**: a human-provided answer or an uploaded document addressing one or
  more gaps.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a project with N genuine information gaps, the human is asked about
  those N things before the browser automation runs, not discovered one at a time across
  multiple full form-filling re-runs.
- **SC-002**: A project with no real gaps completes with the same quality of result as
  today (spec 002/003), with no extra human-interaction step imposed on it.
- **SC-003**: The final compliance result's `needs_human_input` (spec 003's reactive
  fallback) is empty or smaller than it would have been without this feature, for the
  same project, because likely-missing categories were already surfaced upfront.

## Assumptions

- One summarization LLM call is the default path; a project too large for that call's
  context window falls back to summarizing in chunks and combining those into one
  coherent summary (map-reduce) — the mechanism is an implementation decision for
  `/speckit-plan`, not specified here, but the *output* must still read as one coherent
  document, not a list of per-chunk notes.
- Gaps are categories of information, not tied to a specific checker form field (the
  actual form fields aren't known yet at this stage — the form hasn't been opened) —
  contrast with spec 003's `UnresolvedQuestion`, which is tied to a specific `field_id`
  discovered by running the browser.
- This feature changes the *context source* for form-filling (summary instead of
  retrieval) but does not require removing `code_index.py` — that retrieval code stays
  available as the fallback path for spec 003's reactive `needs_human_input` questions
  (FR-006), where the summary alone might not have enough detail for a very specific
  follow-up question.
