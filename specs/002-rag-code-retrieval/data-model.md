# Data Model: Full-Codebase Analysis via Retrieval

All entities below are transient, in-memory, and scoped to a single
`/api/v1/compliance-check` request — none are persisted (consistent with
`specs/001-compliance-check-agent/spec.md`).

## CodeChunk

A bounded slice of the Repomix representation, indexed for retrieval.

| Field | Type | Notes |
|---|---|---|
| `file_path` | string | Source file path as reported by Repomix; used as citation/metadata, not shown to the end user today. |
| `content` | string | The chunk's text — normally one whole source file; split further only if a single file exceeds the embedding/context budget. |

**Validation rules**: a chunk MUST be non-empty; empty files from Repomix are skipped
(nothing to index).

## ProjectIndex

The retrieval index built once per compliance-check request, from all of a project's
`CodeChunk`s.

| Field | Type | Notes |
|---|---|---|
| `chunks` | CodeChunk[] | Parsed from the Repomix output for this request. |
| `vector_store` | (LlamaIndex `SimpleVectorStore`, in-memory) | Built from `chunks`; not serialized, discarded after the request. |

**Relationships**: one `ProjectIndex` per compliance-check run; replaces the single
`code_context` string currently passed to `_ask_llm_for_answer` in `compliance_agent.py`.

**State transitions**: `built` (once, at the start of `run_compliance_check`) →
`queried` (once per checker question, read-only) → discarded (end of request, no
transition needed — it's garbage-collected with the request).

## RetrievedContext

The result of querying a `ProjectIndex` with one checker question's text.

| Field | Type | Notes |
|---|---|---|
| `question` | string | The checker question text (already scraped/stripped in `compliance_agent.py`). |
| `chunks` | CodeChunk[] | Top-k chunks by relevance to `question`; replaces today's fixed-prefix `code_context[:MAX_CODE_CONTEXT_CHARS]`. |

**Validation rules**: `chunks` MAY be empty (project has nothing relevant to this
question) — this is a valid, expected state that must still let `_ask_llm_for_answer`
run and return a low-confidence/`needs_human_input` answer (FR-005, edge case in spec.md:
"NO chunk of the project is relevant").
