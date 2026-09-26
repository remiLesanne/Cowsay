# Tasks: Full-Codebase Analysis via Retrieval

**Input**: Design documents from `specs/002-rag-code-retrieval/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested in spec.md / by the user — no automated test suite exists yet
for this backend (tracked separately in README.md). Validation is manual, via
`quickstart.md`, per the Polish phase below.

**Organization**: tasks are grouped by user story (spec.md: US1 = correct verdict on a
large project, US2 = reasonable turnaround/cost) so each can be validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: which user story this task belongs to (US1, US2)
- Paths are relative to `backend/` unless stated otherwise

## Phase 1: Setup

**Purpose**: get the new dependency in place before any retrieval code is written

- [ ] T001 Add `llama-index-core` and `llama-index-embeddings-huggingface` to
      `backend/requirements.txt`
- [ ] T002 Add a step to `backend/Dockerfile` that pre-downloads the chosen embedding
      model at image build time (per `research.md`: avoid a slow, network-dependent
      first request in production)
- [ ] T003 Confirm `pip install -r backend/requirements.txt` succeeds locally and the
      chosen embedding model loads (smoke test, no code committed for this step)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the retrieval module that both user stories depend on

**⚠️ CRITICAL**: neither user story can be implemented until this phase is complete

- [ ] T004 Create `backend/code_index.py` with a `CodeChunk` type per `data-model.md`
      (fields: `file_path: str`, `content: str`; a chunk MUST be non-empty — empty files
      from Repomix are skipped, not indexed)
- [ ] T005 In `backend/code_index.py`, implement chunking: split the Repomix
      representation into one `CodeChunk` per source file (per `research.md` "chunk by
      source file, not fixed-size windows"); add a fallback character-based sub-split
      only for a single file whose content would exceed the embedding model's input
      limit
- [ ] T006 In `backend/code_index.py`, implement `ProjectIndex` per `data-model.md`:
      builds an in-memory LlamaIndex `SimpleVectorStore` from a list of `CodeChunk`s
      using the local HuggingFace embedding model chosen in `research.md`; no
      persistence, scoped to one call
- [ ] T007 In `backend/code_index.py`, implement `ProjectIndex.query(question: str) ->
      RetrievedContext` per `data-model.md`: returns the top-k most relevant
      `CodeChunk`s for `question`; MUST be able to return an empty list (no chunk
      relevant) without raising — per data-model.md Validation rules and FR-005, this is
      a valid state, not an error

**Checkpoint**: `code_index.py` can turn a Repomix string into a queryable index —
neither user story wires it into `compliance_agent.py` yet.

---

## Phase 3: User Story 1 - Get a correct verdict on a large project (Priority: P1) 🎯 MVP

**Goal**: replace fixed-prefix truncation with per-question retrieval so facts outside
today's ~12,000-character window are still found.

**Independent Test**: per `quickstart.md` — a project with a relevant fact placed past
the old truncation window gets that checker question answered correctly and it does NOT
appear in `needs_human_input`.

### Implementation for User Story 1

- [ ] T008 [US1] In `backend/compliance_agent.py`, build one `ProjectIndex` (from
      `code_index.py`) at the start of `run_compliance_check`, from the full
      `code_context` argument — replacing today's single fixed string kept for the
      whole run
- [ ] T009 [US1] In `backend/compliance_agent.py`, change `_ask_llm_for_answer` to
      accept a `RetrievedContext` (or call `ProjectIndex.query(question)` itself) instead
      of receiving the pre-truncated `code_context[:MAX_CODE_CONTEXT_CHARS]` string;
      build the prompt's "Codebase representation" section from the retrieved chunks'
      content instead
- [ ] T010 [US1] Remove `MAX_CODE_CONTEXT_CHARS` truncation from
      `backend/compliance_agent.py` now that retrieval bounds the context by relevance
      instead of by a fixed prefix
- [ ] T011 [US1] Preserve existing behavior when `ProjectIndex.query` returns no chunks:
      `_ask_llm_for_answer` must still produce a low-confidence /
      `needs_human_input`-eligible answer (per FR-005), not fail or fabricate
- [ ] T012 [US1] Run `quickstart.md`'s "Setup" and "Run" steps manually against a local
      backend; confirm the "Expected outcome" (deliberately-placed fact is found and
      answered correctly)
- [ ] T013 [US1] Run `quickstart.md`'s "Regression check" against the existing small
      test project from `specs/001-compliance-check-agent/spec.md`; confirm
      `results_text` and `needs_human_input` are unchanged from before this feature
      (SC-003)

**Checkpoint**: large-project compliance checks now use retrieval; small-project
behavior is unchanged. This alone is a shippable increment (MVP).

---

## Phase 4: User Story 2 - Reasonable turnaround time and cost (Priority: P2)

**Goal**: confirm the retrieval approach doesn't regress LLM call count or wall-clock
time versus today.

**Independent Test**: per spec.md — LLM call count stays proportional to the number of
checker questions (not to project size); wall-clock time stays the same order of
magnitude as a small-project run today.

### Implementation for User Story 2

- [ ] T014 [US2] Verify (by inspection of `compliance_agent.py` after T008-T011) that
      exactly one LLM call is still made per checker question — indexing/embedding in
      `code_index.py` must not itself call the LLM (per FR-003; embeddings are computed
      locally, per `research.md`, not via the Z.AI API)
- [ ] T015 [US2] Manually time a compliance-check run on a large test project (per
      `quickstart.md` setup) end-to-end; confirm it completes within the same order of
      magnitude as a small-project run (SC-002) — if indexing dominates the time budget,
      note it in `research.md` as a follow-up rather than silently accepting a regression

**Checkpoint**: both user stories validated; feature ready to merge.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T016 [P] Update `README.md`: add `llama-index-core` /
      `llama-index-embeddings-huggingface` under the backend's dependencies, remove any
      mention of the old fixed-truncation limitation from "Status / what's left" (per
      constitution Principle V — README must reflect current state)
- [ ] T017 [P] Update `specs/001-compliance-check-agent/spec.md` Edge Cases: the "Known
      gap, not yet solved" note about large-project context truncation is resolved by
      this feature — update or cross-reference rather than leaving it stale
- [ ] T018 Re-run `quickstart.md` end-to-end one more time after T016-T017 to confirm
      nothing broke from the doc-only changes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Setup — BLOCKS both user stories
- **User Story 1 (Phase 3)**: depends on Foundational; no dependency on US2
- **User Story 2 (Phase 4)**: depends on Foundational and on US1's integration existing
  (T014 inspects the code T008-T011 produced) — not independent of US1 in this feature,
  unlike the general template assumption, because US2 is a verification of US1's
  implementation rather than separate functionality
- **Polish (Phase 5)**: depends on US1 (and US2's confirmation) being complete

### Parallel Opportunities

- T001 and T002 (Setup) can run in parallel — different files
- T016 and T017 (Polish, docs) can run in parallel — different files
- T004-T007 (Foundational) are sequential within `code_index.py` (each builds on the
  previous function existing) — not parallelizable despite being one file

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational)
2. Complete Phase 3 (User Story 1) — this alone fixes the core problem (large projects
   get correct answers)
3. **STOP and VALIDATE**: run `quickstart.md` in full (T012-T013)
4. User Story 2 (Phase 4) is a verification pass on what already shipped, not new
   user-facing behavior — do it before merging, but it doesn't block demoing US1

### Incremental Delivery

1. Setup + Foundational → retrieval module exists but isn't wired in yet (no observable
   change to the API)
2. User Story 1 → the actual fix ships; large projects now get correct compliance
   verdicts
3. User Story 2 → confidence check that it didn't get slower/more expensive
4. Polish → docs catch up (constitution requirement, not optional)

---

## Notes

- No `[P]` markers inside Phase 2 or Phase 3 beyond what's listed — most tasks in this
  feature edit the same two files (`code_index.py`, `compliance_agent.py`) sequentially,
  so true parallelism is limited; don't force `[P]` where tasks touch the same file.
- Commit after each checkpoint (Foundational done, US1 done, US2 done, Polish done) —
  matches the project's git workflow convention (one branch for this whole feature,
  already created: `feature/rag-code-retrieval`; push after each working checkpoint).
