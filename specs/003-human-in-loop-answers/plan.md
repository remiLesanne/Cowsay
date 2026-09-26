# Implementation Plan: Human-in-the-Loop Answers for Unresolved Questions

**Branch**: `feature/human-in-the-loop-answers` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-human-in-loop-answers/spec.md`

## Summary

Add a server-side session cache keyed by a returned `session_id`, holding the already
built `ProjectIndex` (from spec 002) and the human answers accumulated so far. Extend
`needs_human_input` entries with `field_id`/`type`/`options`. Add a resume endpoint that
takes `session_id` + new human answers, validates multiple-choice answers against real
options, and re-runs the Playwright loop — applying human answers directly instead of
calling the LLM for those fields — reusing the cached index instead of rebuilding it.
Frontend renders unresolved questions as selectable choices (radio/checkbox buttons) or
a text input, and posts back to the resume endpoint.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript/Next.js (frontend) — unchanged.

**Primary Dependencies**: none new on the backend (reuses existing `code_index.py`,
`compliance_agent.py`, FastAPI). No new frontend dependency.

**Storage**: in-memory dict (module-level, process-local) for the session cache — not a
database. Explicit trade-off per spec.md Assumptions (single-instance only).

**Testing**: manual, per this plan's `quickstart.md` (no automated suite yet — same gap
tracked in README.md, not introduced or fixed here).

**Target Platform**: same as existing backend/frontend.

**Project Type**: web-service + web-app (existing structure).

**Performance Goals**: a resume round-trip must not re-run Repomix or re-build the
`ProjectIndex` (SC-001 depends on this — otherwise resuming would be as slow as a fresh
upload, defeating the purpose for large projects per spec 002's research.md).

**Constraints**: validation of a multiple-choice answer MUST happen before launching
Playwright (SC-002 — no wasted browser run on a doomed request); session TTL bounded
(FR-007) to avoid unbounded memory growth from abandoned sessions.

**Scale/Scope**: single compliance-check session at a time is the common case for this
project's scale; the in-memory dict handles multiple concurrent sessions fine (keyed by
id) but doesn't survive a process restart — acceptable per Assumptions.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (drive the real tool, never reimplement)**: PASS — human answers are
  still applied by clicking the real checker's DOM elements, same as LLM answers today;
  we don't reimplement the form's logic, we just skip the LLM call for fields the human
  already answered.
- **Principle II (no silent guessing)**: PASS — this feature exists specifically to let
  a human resolve what the LLM couldn't, without ever fabricating an answer; invalid
  answers are rejected, not silently coerced.
- **Principle III (spec-driven development)**: PASS — this plan.
- **Principle IV (production-shaped, not a POC)**: the in-memory session cache is a
  deliberate, bounded, documented trade-off (TTL + explicit "won't survive restart"
  note) rather than an accidental shortcut — consistent with how spec 002 documented its
  own 500MB indexing gap instead of hiding it. PASS with a noted limitation.
- **Principle V (README stays current)**: README.md must document the new resume
  endpoint and its session-cache trade-off once shipped. Tracked as a task.

No violations — Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-human-in-loop-answers/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)

(no contracts/ subfolder — the new/changed endpoints are documented directly in
 data-model.md and quickstart.md, consistent with how spec 002 skipped it for an
 internal-only change; here the API DOES change, so the new request/response shapes
 are spelled out in data-model.md instead of a separate contracts file, to avoid
 duplicating the same information twice for a feature this size)
```

### Source Code (repository root)

```text
backend/
├── main.py                  # + POST /api/v1/compliance-check/{session_id}/answer
├── compliance_agent.py      # run_compliance_check gains human_answers param;
│                            # needs_human_input entries gain field_id/type/options
├── session_store.py         # NEW: in-memory {session_id: {project_index, answers,
│                            # expires_at}} cache with TTL cleanup
└── code_index.py            # unchanged (ProjectIndex already reusable)

frontend/
├── app/analyse/page.tsx     # renders needs_human_input as radio/checkbox/text inputs,
│                            # posts to the resume endpoint, merges results
└── app/lib/api.ts           # + resumeComplianceCheck(sessionId, answers)
```

**Structure Decision**: extend the existing `backend/` and `frontend/` structure; one
new backend module (`session_store.py`) to keep the caching concern separate from both
`compliance_agent.py` (browser/LLM loop) and `code_index.py` (retrieval), matching the
same single-responsibility approach used for spec 002's `code_index.py`.

## Complexity Tracking

No constitution violations — table not needed.
