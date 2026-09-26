# Feature Specification: EU AI Act Compliance-Check Agent

**Feature Branch**: `feature/compliance-check-agent`

**Created**: 2026-09-26

**Status**: Implemented (spec written retroactively — feature was built before Spec Kit
was adopted on this repo; see Governance in constitution.md)

**Input**: User description: "build an agent that will take the code from repomix and
will fill the compliance checker form on
https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/
with the info it can find in the code, then give back the answer from the form"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a compliance verdict for a codebase (Priority: P1)

A developer uploads their project's source code (file or zip). The system determines
whether that project complies with the EU AI Act by running the official checker on its
behalf and returns the checker's real recommendation.

**Why this priority**: This is the core value of the whole app — everything else (Repomix
conversion, upload handling) exists only to serve this outcome.

**Independent Test**: `POST /api/v1/compliance-check` with a small real code file and no
company context; confirm the response's `results_text` matches what a human filling the
same form with the same facts would get.

**Acceptance Scenarios**:

1. **Given** a code file that clearly describes an EU-market AI system, **When** it is
   submitted, **Then** the response's `results_text` contains the checker's own
   recommendation text (not a locally-computed approximation).
2. **Given** the same code, **When** submitted twice, **Then** both runs answer the same
   questions the same way (deterministic given deterministic LLM output) and reach the
   same recommendation.

---

### User Story 2 - Surface what the AI couldn't determine (Priority: P1)

When the code doesn't contain enough information to answer a checker question
confidently, the system tells the human what's missing instead of guessing.

**Why this priority**: Explicit product requirement — guessing silently would make the
compliance verdict untrustworthy, defeating the purpose of the tool.

**Independent Test**: Submit a code file with no bearing on a given question (e.g. no
mention of EU market, biometric use, etc.) and confirm that question appears in
`needs_human_input` with a reasoning string, and the overall response still completes
(doesn't fail or hang).

**Acceptance Scenarios**:

1. **Given** code with no information relevant to a required question, **When** the
   agent answers it with low confidence, **Then** that question and the model's stated
   reasoning appear in `needs_human_input`.
2. **Given** optional `company_name`/`company_context` are supplied, **When** they answer
   a question the code alone couldn't, **Then** that question is answered normally and
   does NOT appear in `needs_human_input`.

---

### User Story 3 - Convert a project to AI-readable text (Priority: P2)

A developer (or the compliance agent itself) needs an uploaded project turned into a
single AI-friendly text representation, independent of the compliance check.

**Why this priority**: Useful standalone (e.g. for other future AI features on this
codebase) and is a hard dependency of User Story 1, but has value on its own.

**Independent Test**: `POST /api/v1/analyses` with a zip; confirm the response contains a
non-empty Repomix representation and the correct file count/list.

**Acceptance Scenarios**:

1. **Given** a valid zip under the size limit, **When** uploaded, **Then** the response
   contains a Repomix representation and metadata listing the source files found.
2. **Given** a zip containing a zip-slip path (`../../etc/passwd`), **When** uploaded,
   **Then** the request is rejected with 400, no file is written outside the temp project
   directory.

### Edge Cases

- What happens when the checker form's question tree changes on the live site (new
  questions, renamed fields)? → The DOM-scraping approach (`GET_VISIBLE_FIELDS_JS` in
  `compliance_agent.py`) is generic (any visible radio/checkbox/text field), so new
  questions are picked up automatically; only a structural change to how questions are
  *rendered* (not just added) would require code changes.
- What happens when the LLM API is unreachable or misconfigured? → `_ask_llm_for_answer`
  raises `HTTPException` (503 for missing key, 502 for a failed call), surfaced to the
  caller rather than silently failing.
- What happens when the form never reaches completion (e.g. a required text field the
  agent can't fill)? → The loop stops after `MAX_ITERATIONS` (30) with whatever
  `results_text` the page shows at that point (may still say "Incomplete"); `is_complete`
  reflects this so the caller can detect it.
- What happens with a project too large for the LLM's context? → **Resolved by
  `specs/002-rag-code-retrieval/`**: the fixed `MAX_CODE_CONTEXT_CHARS` truncation was
  replaced with per-question retrieval (`code_index.py`) so relevant facts are found
  regardless of position in the project. Validated up to ~100KB synthetic projects;
  a true 500MB project is still impractical in a single synchronous request at current
  indexing throughput (~90 min) — see that spec's `research.md` for the remaining gap.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept an uploaded code file or zip archive and convert it to a
  Repomix text representation before compliance analysis.
- **FR-002**: System MUST drive the actual official checker page (Playwright) rather than
  reimplementing its question logic, so results are guaranteed identical to the real tool.
- **FR-003**: System MUST answer each dynamically-revealed question using an LLM call
  grounded in the Repomix code context plus optional company context.
- **FR-004**: System MUST NOT silently guess when the LLM's answer has low confidence or
  is empty — such questions MUST be collected and returned to the caller.
- **FR-005**: System MUST return the checker's own recommendation text, scraped from the
  live page, not a locally-recomputed one.
- **FR-006**: System MUST reject uploads whose extension isn't in the allow-list, that
  exceed the configured size limits, or whose zip contents attempt path traversal.
- **FR-007**: System MUST bound total automation time (iteration cap) so a stuck form
  cannot hang a request indefinitely.

### Key Entities

- **Compliance check result**: `{ is_complete, results_text, questions_answered,
  needs_human_input[] }` — one per submitted project; not persisted (stateless request).
- **Question/answer pair**: transient, in-memory only during a single check run
  (`processed` dict in `run_compliance_check`); not stored after the response is returned.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a project whose facts are fully present in its code, the returned
  `results_text` matches what a human would get filling the same form by hand (verified
  manually during implementation against the live site).
- **SC-002**: No question is ever answered with fabricated information not traceable to
  the code/context or explicit low-confidence disclosure in `needs_human_input`.
- **SC-003**: A compliance check completes (success or documented `needs_human_input`
  list) without manual intervention, within `MAX_ITERATIONS` form-filling rounds.

## Assumptions

- The official checker's page structure (WS Form plugin, radio/checkbox/text fields,
  "Your results" / "Save your results" text markers) remains stable enough for DOM
  scraping; a significant redesign of the site would require updating
  `GET_VISIBLE_FIELDS_JS` / `_extract_results_section`.
- One AI system per submission (matches the checker's own instruction: "complete this
  form for each individual AI system").
- The LLM (Z.AI GLM models) is reachable and the `ZAI_API_KEY` is configured; no offline
  fallback is in scope.
- Cross-checking the checker's recommendation against the AI Act article text itself, and
  a written "summary of the verification", are separate future features (see README) —
  out of scope for this spec, which only covers getting the checker's own verdict.
