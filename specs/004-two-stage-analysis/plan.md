# Implementation Plan: Two-Stage Analysis — Understand, Then Fill

**Branch**: `feature/two-stage-analysis` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

## Summary

Insert a summarization stage before the existing Playwright form-filling loop. New
endpoints: `analyze` (repomix + one LLM summarization call → summary + gaps + session),
`resolve-gaps` (merge a human answer or an extra document into context, regenerate the
summary), `run` (the actual form-filling, using the summary as context instead of
per-question retrieval — spec 002's `code_index.py` stays but is no longer called during
the main run; spec 003's `/answer` resume endpoint is untouched and still the fallback
for anything the summary didn't cover).

## Technical Context

**Primary Dependencies**: none new — reuses `httpx` (LLM calls), existing session store.

**Storage**: extends the existing in-memory `ComplianceSession` (spec 003) with
`code_context`, `summary`, `gaps`, and `extra_documents` fields. Still single-process,
30min TTL — same documented trade-off as spec 003.

**Performance Goals / Constraints**: this does NOT reduce the number of per-question LLM
calls during form-filling (still one per discovered checker question — see
`research.md`), so it is not expected to fix the raw per-call latency observed with
`glm-4.5-flash`. Its win is structural: gaps are surfaced once, before the (slow)
browser run, instead of only being discoverable by running the whole form once already.

## Constitution Check

- **Principle I**: unaffected — the checker form is still driven directly, never
  reimplemented.
- **Principle II (no silent guessing)**: reinforced — gaps are explicit, named, and
  shown to the human before form-filling proceeds (FR-007).
- **Principle III**: this plan.
- **Principle IV**: summarization reuses the existing LLM call path (no new external
  dependency); the extra LLM call is a real, justified cost (spec.md "Why this
  replaces...") not an accidental one.
- **Principle V**: README.md must be updated once shipped — tracked as a task.

No violations.

## Project Structure

```text
backend/
├── main.py                    # + POST .../analyze, .../resolve-gaps, .../run
├── project_summary.py         # NEW: generate_project_summary(code_context, extra) -> {summary, gaps}
├── compliance_agent.py        # run_compliance_check_with_index gains a
│                               # summary_context path (used instead of
│                               # per-question code_index retrieval when present)
├── session_store.py           # ComplianceSession: + code_context, summary,
│                               # gaps, extra_documents fields
└── code_index.py              # unchanged; still imported for spec 003's
                                # existing fallback behavior, just not called
                                # from the new default run path

frontend/
├── app/lib/api.ts             # + analyzeProject, resolveGap, runComplianceCheck (session-based)
├── app/page.tsx               # upload now calls analyzeProject instead of
│                               # the old direct runComplianceCheck
└── app/analyse/page.tsx       # + summary/gaps review step before the existing
                                # results view; existing needs_human_input UI
                                # (spec 003) reused unchanged for the fallback
```

**Structure Decision**: one new backend module (`project_summary.py`) for the
summarization concern, matching the established pattern (`code_index.py` for
retrieval, `session_store.py` for caching) — each concern its own file.

## Complexity Tracking

No constitution violations — table not needed.
