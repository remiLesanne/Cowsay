# Implementation Plan: Full-Codebase Analysis via Retrieval

**Branch**: `feature/rag-code-retrieval` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-rag-code-retrieval/spec.md`

## Summary

Replace the fixed-size truncation of the Repomix code representation
(`code_context[:MAX_CODE_CONTEXT_CHARS]` in `compliance_agent.py`) with per-question
retrieval: chunk the project by file, embed the chunks locally (no external embeddings
API — see `research.md`), and for each checker question retrieve only the top-k most
relevant chunks before calling the LLM. Implemented with LlamaIndex (project owner's
explicit choice). No change to the existing Playwright question-answering loop or the
public API contract of `/api/v1/compliance-check`.

## Technical Context

**Language/Version**: Python 3.11 (matches existing `backend/Dockerfile`)

**Primary Dependencies**: `llama-index-core` (indexing/retrieval),
`llama-index-embeddings-huggingface` + a small sentence-transformers model (local
embeddings — see `research.md` for why not Z.AI). Existing deps (`httpx`, `playwright`)
unchanged.

**Storage**: N/A — in-memory `SimpleVectorStore` per request, not persisted (see
`data-model.md`).

**Testing**: manual end-to-end validation per `quickstart.md` (no automated test suite
exists yet for this backend — tracked as a general gap in README.md "Status", not
introduced or fixed by this feature).

**Target Platform**: Linux container (AWS ECS Fargate), same as existing backend.

**Project Type**: web-service (existing FastAPI backend, `backend/` directory)

**Performance Goals**: compliance-check wall-clock time stays same order of magnitude as
today for a small project (SC-002); LLM call count per check stays ~1 per checker
question, not proportional to project size (FR-003).

**Constraints**: no new paid API dependency (local embeddings, per `research.md`); no
new persistent infrastructure (in-memory index only, per `research.md`).

**Scale/Scope**: projects up to the upload size limit (separately tracked at ~500MB,
see spec.md Assumptions) must be indexable within a single request's lifetime.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (drive the real tool, never reimplement)**: N/A to this feature — it
  changes how the LLM's *input* is assembled, not how the checker form itself is driven.
  PASS.
- **Principle II (no silent guessing)**: preserved by design — `RetrievedContext.chunks`
  MAY be empty, and `_ask_llm_for_answer` still returns low-confidence /
  `needs_human_input` in that case rather than fabricating an answer (data-model.md
  Validation rules). PASS.
- **Principle III (spec-driven development)**: this plan is itself compliance with that
  principle. PASS.
- **Principle IV (production-shaped, not a POC)**: local embeddings avoid an unjustified
  new paid dependency; in-memory-only index avoids unjustified new infrastructure
  (research.md trade-offs explicitly reasoned, not left implicit). PASS.
- **Principle V (README stays current)**: README.md's "Status / what's left" and
  "Required env vars" sections MUST be updated once this ships (new deps, no new env
  var). Tracked as a task, not a gate failure.

No violations — Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)

(no contracts/ — this feature changes internal implementation only; the
 /api/v1/compliance-check request/response contract from specs/001 is unchanged)
```

### Source Code (repository root)

```text
backend/
├── main.py                 # unchanged: still calls run_compliance_check(...)
├── compliance_agent.py     # changed: _ask_llm_for_answer receives retrieved
│                           # chunks instead of a fixed-size code_context slice
├── code_index.py           # NEW: builds a per-request ProjectIndex from the
│                           # Repomix representation (chunking + local
│                           # embeddings + retrieval), per data-model.md
├── requirements.txt        # + llama-index-core, llama-index-embeddings-huggingface
└── Dockerfile              # may need the embedding model pre-downloaded/cached
                             # to avoid a slow first request in production
```

**Structure Decision**: single existing web-service (`backend/`), no new top-level
component. One new module (`code_index.py`) to keep the retrieval concern separate from
`compliance_agent.py`'s existing Playwright/LLM-loop concern (constitution doesn't
mandate a structure here, but keeping single-responsibility modules is consistent with
Principle IV's "production-shaped" spirit).

## Complexity Tracking

No constitution violations — table not needed.
