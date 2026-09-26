# Feature Specification: Full-Codebase Analysis via Retrieval

**Feature Branch**: `feature/rag-code-retrieval`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "make a 500MB project be fully analyzed on the whole
process, including by the AI" — the compliance-check agent currently truncates the
Repomix code representation to a fixed character limit before sending it to the LLM, so
facts that live outside that window are invisible to the agent no matter how large the
upload-size limit is raised. Retrieve only the code relevant to each question instead of
truncating a fixed prefix.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a correct verdict on a large project (Priority: P1)

A developer submits a large project (up to several hundred MB of source) for a compliance
check. A fact relevant to one of the checker's questions lives in a file that would fall
outside today's fixed truncation window. The system still finds and uses that fact when
answering the question.

**Why this priority**: This is the entire point of the feature — without it, raising the
upload size limit is cosmetic; large projects would still get wrong or "low confidence"
answers whenever the relevant fact isn't near the start of the code representation.

**Independent Test**: Build a test project where a single relevant fact (e.g. "this
system processes biometric data") sits in a file placed after where today's fixed
truncation would cut off. Submit it and confirm the corresponding checker question is
answered correctly and is NOT listed in `needs_human_input`.

**Acceptance Scenarios**:

1. **Given** a project larger than the current fixed context window, **When** a
   compliance check is run, **Then** every question whose answer is determinable from
   *some* file in the project is answered correctly, regardless of that file's position
   in the project.
2. **Given** the same large project, **When** compared to today's behavior (fixed
   truncation), **Then** the number of questions correctly answered is greater than or
   equal to before, never worse.

---

### User Story 2 - Reasonable turnaround time and cost (Priority: P2)

A developer submits a large project and expects the compliance check to complete without
an excessive wait or an unbounded number of LLM calls.

**Why this priority**: Retrieval must not become slower or more expensive than the
current approach in a way that makes the feature impractical for the team's (free-tier)
LLM quota.

**Independent Test**: Run a compliance check on a large project and measure end-to-end
time and number of LLM calls; compare against a small-project baseline run today.

**Acceptance Scenarios**:

1. **Given** a large project, **When** a compliance check runs, **Then** the number of
   LLM calls made is proportional to the number of checker questions asked, not to the
   size of the project (i.e. retrieval happens locally, not via LLM calls per chunk).
2. **Given** the same large project run twice, **When** compared, **Then** total time is
   within the same order of magnitude both times (no unbounded/runaway indexing step).

### Edge Cases

- What happens when NO chunk of the project is relevant to a given question? → Must
  behave the same as today: low-confidence / `needs_human_input`, not a fabricated
  answer (per existing constitution Principle II).
- What happens when the project is small enough that everything already fit in the old
  fixed window? → Must produce the same answers as before (no regression for the
  already-working case).
- What happens when the project contains no extractable text (e.g. all binary/media
  files, Repomix output nearly empty)? → Same as today: proceeds with whatever Repomix
  produced; not a new failure mode introduced by this feature.
- What happens if building the retrieval index itself fails or times out? → Must fail
  loudly (clear error to the caller), not silently fall back to guessing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST answer each compliance-checker question using only the parts
  of the project's code that are relevant to that specific question, selected from the
  full project rather than a fixed-size prefix.
- **FR-002**: System MUST support projects up to the (separately tracked) upload size
  limit without silently dropping content the way today's fixed character truncation
  does.
- **FR-003**: System MUST NOT increase the number of LLM calls per compliance check
  beyond one (or a small constant) per checker question — relevance selection MUST
  happen without an LLM call per chunk of the project.
- **FR-004**: System MUST preserve current behavior (no answer degradation) for projects
  that already fit entirely within today's fixed context window.
- **FR-005**: System MUST surface a clear, actionable error if the relevance-selection
  step itself fails, rather than proceeding with an empty or wrong context silently.

### Key Entities

- **Code chunk**: a bounded slice of the Repomix representation (e.g. by file or by
  fixed token/character window), the unit that relevance selection operates over.
- **Relevance index**: a per-compliance-check, in-memory/transient structure built from
  the project's chunks, used to select which chunks to include per question. Not
  persisted beyond the request (consistent with the existing compliance-check result not
  being persisted — see `specs/001-compliance-check-agent/spec.md`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a project where a relevant fact is deliberately placed outside today's
  fixed truncation window, the corresponding question is answered correctly (previously
  it would have been mis-answered or flagged as needing human input).
- **SC-002**: A compliance check on a large project completes in the same order of
  magnitude of wall-clock time as one on a small project today (no multi-minute-per-file
  blowup).
- **SC-003**: No regression: every question answered correctly today on the existing
  small test cases is still answered correctly after this change.

## Assumptions

- "Fully analyzed... including by the AI" (user's phrasing) means: every part of the
  project is *eligible* to be found and used if relevant to some question — not that the
  entire project is read verbatim by the LLM in one call, which is infeasible at the
  target scale (see `specs/001-compliance-check-agent/spec.md` Edge Cases: "Known gap,
  not yet solved").
- The team has chosen to build relevance selection with an existing retrieval library
  (LlamaIndex) rather than a hand-rolled chunking/embedding pipeline, per explicit
  direction from the project owner (2026-09-26) — this is a technology constraint to
  carry into `/speckit-plan`, not itself a functional requirement.
- The existing Playwright question-answering loop (`compliance_agent.py`) and its
  "surface low-confidence answers instead of guessing" behavior are unchanged by this
  feature; only how the code context for each LLM call is assembled changes.
- Raising the upload size limits (`MAX_FILE_SIZE`, `MAX_ZIP_FILE_SIZE`,
  `MAX_ARCHIVE_SIZE`) to allow ~500MB projects is a prerequisite/companion change,
  tracked separately, not itself part of this spec's functional requirements.
