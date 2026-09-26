# Research: Full-Codebase Analysis via Retrieval

## Decision: LlamaIndex for indexing/retrieval

**Rationale**: Purpose-built for RAG (vs. LangChain's broader scope, or LangGraph which
is agent-orchestration, not retrieval). Minimal code to go from "list of text chunks" to
"top-k relevant chunks for a query". Explicit direction from project owner (2026-09-26).

**Alternatives considered**: hand-rolled chunking + cosine similarity (more code to
write/maintain for no benefit at this scale); LangChain's retrieval abstractions (heavier
dependency for the same result); map-reduce summarization of every chunk before asking
any question (rejected in the original feature discussion — violates FR-003, one LLM
call per chunk regardless of whether it's ever relevant).

## Decision: Local embedding model, not Z.AI

**Rationale**: Z.AI's public API (`api.z.ai/api/paas/v4`) does not serve an embeddings
endpoint — confirmed via community reports of `embeddings` returning "Unknown Model" /
404 on that host (embeddings from this provider are only available through a different,
domestic endpoint the team doesn't have access to). Using a local HuggingFace embedding
model (via `llama-index-embeddings-huggingface`, e.g. a small general-purpose sentence
model) avoids depending on an unavailable API and keeps the feature free to run — no
additional API key, no additional network dependency, consistent with the project's
free-tier constraint.

**Alternatives considered**: calling out to another provider (Mistral, OpenAI) just for
embeddings — rejected, adds a second API key/dependency for a feature that doesn't need
one; Z.AI embeddings — rejected, not available on the endpoint this project uses.

**Trade-off accepted**: first request pays a one-time cost to download the embedding
model (a few hundred MB) into the container image or a persisted cache; local embedding
inference adds CPU time per compliance-check (bounded by project size, not by network
latency).

## Decision: Chunk by source file, not fixed-size windows

**Rationale**: Repomix's output already delimits each source file explicitly (both its
`xml` and `markdown` styles). Chunking by file is a natural semantic unit for "is this
fact present in the project" questions, avoids splitting a relevant snippet across two
chunks at an arbitrary boundary, and needs no extra parsing beyond what Repomix already
produces. A file whose size alone would blow the LLM's context (rare) is handled by a
secondary character-based split as a fallback, not the general case.

**Alternatives considered**: fixed-size token windows across the whole blob (simpler to
implement, but risks splitting a relevant fact mid-sentence/mid-function, right where it
would then fail to retrieve well); one chunk per function/class via a code-aware AST
splitter (more precise, but Repomix's output format doesn't expose a per-language AST
without extra parsing work not justified at this stage).

## Decision: Top-k retrieval per question, no persistence

**Rationale**: Matches the existing compliance-check request model — everything is
in-memory for the duration of one HTTP request (`specs/001-compliance-check-agent/spec.md`
Key Entities: "not persisted (stateless request)"). Building a fresh in-memory vector
index per request (LlamaIndex's default `SimpleVectorStore`) avoids introducing a
database dependency contrary to constitution Principle IV (production-shaped, but no
unjustified new infrastructure) for a feature that doesn't need cross-request state.

**Alternatives considered**: a persistent vector store (e.g. for caching an index across
repeated checks of the same project) — explicitly out of scope; nothing in the spec asks
for repeat-analysis performance, and it would add real infrastructure (a database) for a
benefit not requested.

## Measured: indexing throughput (discovered during implementation)

Local embedding indexing measured at ~91 KB/s of Repomix text on a small CPU-only
sentence-transformers model (41 chunks / ~100KB project → ~1.1s to index; ~15ms per
retrieval query afterwards — query cost is negligible, indexing is the bottleneck).

**Implication**: this comfortably fixes the original problem (facts anywhere in a project
of up to a few tens of MB are now found correctly — see SC-001 validation). It does
**not** make a 500MB project indexable within a single synchronous HTTP request: at this
throughput, indexing alone would take on the order of 90 minutes. Raising the upload
limit to 500MB (spec.md Assumptions) without addressing this would let a request through
that then times out or hangs.

**Not fixed by this feature — flagged as follow-up, not silently accepted**: making
500MB genuinely practical needs either (a) background/async processing with a
job-status endpoint instead of a synchronous response, (b) a faster embedding model or
batched/GPU inference, or (c) capping how much of a very large project gets indexed
(e.g. skip generated/vendored code more aggressively than today's
`IGNORED_ARCHIVE_DIRECTORIES` already does in `main.py`). None of these were in scope
for this spec (`FR-002` only required "up to the upload limit" without a specific
500MB target time budget) — recorded here so the next person doesn't assume the numeric
500MB target was validated end-to-end.

## Open questions resolved

- **NEEDS CLARIFICATION: embedding provider** → resolved above (local HuggingFace model).
- **NEEDS CLARIFICATION: chunk granularity** → resolved above (per-file, with a fallback
  split for oversized files).
