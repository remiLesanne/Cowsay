# Tasks: Two-Stage Analysis — Understand, Then Fill

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested; manual + scripted validation (same approach as specs 002/003).

## Phase 1: Setup

- [X] T001 No new dependencies — confirmed `backend/requirements.txt` unchanged

## Phase 2: Foundational

- [X] T002 Created `backend/project_summary.py`: `generate_project_summary(code_context,
      extra_context) -> dict` with `summary`/`gaps`, reusing `compliance_agent.py`'s
      `LLM_API_URL`/`LLM_MODEL`/`_get_http_client()` directly (imported, not duplicated)
- [X] T003 Extended `ComplianceSession`: `code_context`, `extra_documents: list[str]`,
      `summary: dict` fields; `create_session(...)` takes `code_context` now
- [X] T004 `run_compliance_check_with_index` gained `summary_context: str | None`; when
      set, used instead of `project_index.query(...)` for the per-field LLM context
      (`code_index.py`/retrieval path untouched, still used when `summary_context` is
      omitted — i.e. by the original spec 002/003 single-call endpoint)

**Checkpoint**: summarization + session storage exist; nothing wired to the API yet.

## Phase 3: User Story 1 - Get a summary with explicit gaps (P1) 🎯 MVP

- [X] T005 [US1] Added `POST /api/v1/compliance-check/analyze` — Repomix +
      `build_project_index` + `generate_project_summary` run concurrently
      (`asyncio.gather`), session created with `code_context`; returns
      `{session_id, summary, gaps}`
- [X] T006 [US1] `analyzeProject(file, companyName?, companyContext?)` added
- [X] T007 [US1] `page.tsx` upload now calls `analyzeProject`, stores
      `{session_id, filename, file_count, summary, gaps}` under a new
      `ai-risk-check-analysis` sessionStorage key, navigates to `/analyse`
- [X] T008 [US1] `analyse/page.tsx` renders the summary + gap list before the
      results section (only shown once `result` exists)

**Checkpoint**: uploading a project shows a summary + gaps — verified live against the
real API (see T014).

## Phase 4: User Story 2 - Resolve gaps before running (P1)

- [X] T009 [US2] Added `POST /api/v1/compliance-check/{session_id}/resolve-gaps` —
      JSON `answers` (gap_id/text pairs) and/or a multipart `file` (read as plain text,
      not Repomix'd) both append to `session.extra_documents`; summary regenerated from
      `code_context + extra_documents` each time
- [X] T010 [US2] `resolveGaps(sessionId, answers, file?)` added
- [X] T011 [US2] `analyse/page.tsx`: per-gap text input + a "déposer un document
      complémentaire" file control; both call `resolveGaps` and replace the displayed
      summary/gaps
- [X] T012 [US2] Added `POST /api/v1/compliance-check/{session_id}/run` — calls
      `run_compliance_check_with_index(..., summary_context=session.summary["summary"])`,
      updates `unresolved_by_field_id`, returns the standard response shape
- [X] T013 [US2] "Lancer le remplissage du formulaire" button added; on success switches
      the page to the existing results view (spec 003's `needs_human_input` UI reused
      as-is for the fallback)
- [X] T014 [US2] **Verified live against the real API** (not just mocked): uploaded a
      plain Flask movie-review app → got a summary + 8 gaps; resolved 2 gaps by typed
      text answer → summary correctly regenerated ("no machine learning or AI
      components... used internally... not placed on the EU market"), those 2 gaps gone
      from the list; ran form-filling → completed with 1 field flagged for human input
      ("Entity type", reasoning: "no AI components, so likely none of the listed entity
      types applicable") — the AI correctly recognized genuine ambiguity instead of
      guessing (constitution Principle II). Did NOT separately test the
      resolve-by-document-upload path live (same code path as the text-answer path,
      lower incremental risk) — flagged, not silently assumed.

**Checkpoint**: full new flow works end-to-end, confirmed live.

## Phase 5: User Story 3 - No unnecessary human involvement (P2)

- [ ] T015 [US3] NOT run live (would need a second full ~80s+ form-filling run against
      the free-tier model purely to confirm a negative — no extra gaps requested — after
      the flow was already validated end-to-end in T014); reasoning: US3 has no new code
      path of its own, it's the natural behavior of US1+US2 when `gaps` comes back empty
      (the "Lancer le remplissage" button is available regardless of gap count). Someone
      should still run it once for real before merging.

## Phase 6: Polish

- [X] T016 [P] `README.md` updated: documents the 3-step flow, notes the original
      single-call endpoint is kept unchanged for backward compatibility (not removed)
- [X] T017 [P] No cross-reference updates needed: specs 002/003's Assumptions describe
      their own endpoints' behavior, which is unchanged (the old `/compliance-check`
      endpoint still exists and works exactly as before)

## Dependencies

Setup → Foundational → US1 (MVP) → US2 (depends on US1's session/summary existing) →
US3 (verification only) → Polish.

## Notes

- `POST /api/v1/compliance-check` (spec 002/003's original single-call endpoint) is not
  deleted by this plan — T016 flags the decision explicitly rather than silently dropping
  API surface a teammate or the frontend's `/compliance` test page might still reference.
