# Research: Two-Stage Analysis

## Decision: This does not reduce per-question LLM call count

**Rationale**: the checker form is branching — its exact questions/options are only
known by driving the real page (constitution Principle I). Replacing per-question RAG
retrieval with a shared summary changes the *quality/coherence* of the context each
per-question LLM call receives, not the *number* of those calls. Live benchmarking during
spec 003 measured 17-83s for a single `glm-4.5-flash` call under real load — that cost is
unchanged by this feature.

**What this feature actually buys**: gaps are identified and can be resolved in ONE
upfront round-trip (one summarization call, cheap relative to a full browser run) instead
of only being discoverable by running the entire slow Playwright loop once, then asking,
then re-running it. For a project with several real gaps, this can save a whole redundant
form-filling run. For a project with none, it costs exactly one extra LLM call.

**Alternatives considered**: keep retrieval as the ONLY context source and just add
upfront gap detection as a separate pass reading the same retrieval index — rejected,
because retrieval is inherently local (per-question chunks) and can't produce a coherent
"here's what I understood about the whole system" statement, which is what the user
explicitly asked for and what makes a gap list trustworthy (a human can sanity-check a
summary; they can't sanity-check "these 5 unrelated code snippets were retrieved").

## Decision: Single summarization call for v1; no map-reduce yet

**Rationale**: matches spec 002's own scoping decision (documented, not solved, the
500MB-scale gap) — solving "project too big for one summarization call" is the same
class of problem, deferred the same way. `MAX_CODE_CONTEXT_CHARS`-style truncation isn't
reintroduced silently: if the code context exceeds a safe prompt size, the LLM is still
given as much as fits, but this is flagged as a known limitation, not hidden.

**Alternatives considered**: chunk-and-combine (map-reduce) summarization — real
solution for large projects, out of scope for this iteration; noted as a follow-up.

## Decision: Gaps are resolved by regenerating the summary, not patching it

**Rationale**: FR-003 requires the summary stay "one coherent document". Appending
"Additional info: ..." fragments after every gap resolution would drift into the same
patchwork problem a summary is meant to avoid. Simpler and more robust: keep the
accumulated extra context (human answers + uploaded document text) and re-run the same
summarization call with `code_context + extra_documents_text` each time a gap is
resolved — more LLM calls during the gap-resolution phase, but each is small/fast
relative to a browser run, and the summary never goes stale or contradicts itself.

**Alternatives considered**: incremental patch of the gaps list only, leaving the summary
prose untouched — rejected, since a newly resolved gap might change the summary's
description of the system itself (e.g. "no info on EU market" resolved by "yes, sold in
France" changes more than just that one bullet point).

## Decision: `code_index.py` (spec 002) stays, but isn't called from the new default path

**Rationale**: spec.md Assumptions — it remains available so a future iteration can wire
it back in as a secondary fallback (e.g., "summary doesn't cover it → try retrieval →
still nothing → ask human") without re-deriving the whole retrieval mechanism. For this
iteration, the fallback for anything the summary doesn't resolve is spec 003's existing
per-question `needs_human_input`/resume flow, unchanged — simpler dependency chain,
avoids building a two-level fallback whose value hasn't been demonstrated yet.
