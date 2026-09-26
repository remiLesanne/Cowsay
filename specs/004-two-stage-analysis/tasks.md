# Tasks: Two-Stage Analysis — Understand, Then Fill

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested; manual + scripted validation (same approach as specs 002/003).

## Phase 1: Setup

- [ ] T001 No new dependencies — confirm `backend/requirements.txt` unchanged

## Phase 2: Foundational

- [ ] T002 Create `backend/project_summary.py`: `generate_project_summary(code_context:
      str, extra_context: str) -> dict` with `summary: str` and `gaps: list[{id, description}]`,
      one LLM call via the shared `_get_http_client()`-style pattern from
      `compliance_agent.py` (reuse `LLM_API_URL`/`LLM_MODEL`, or import them)
- [ ] T003 Extend `backend/session_store.ComplianceSession` (data-model.md): add
      `code_context`, `extra_documents: list[str]`, `summary: dict` fields; extend
      `create_session(...)` accordingly
- [ ] T004 In `backend/compliance_agent.py`, add a `summary_context: str | None` param to
      `run_compliance_check_with_index`; when present, use it (instead of
      `project_index.query(...)`) as the "Codebase excerpts" context for
      `_ask_llm_for_answer` — `code_index.py` stays imported/available but isn't called
      from this path (research.md)

**Checkpoint**: summarization + session storage exist; nothing wired to the API yet.

## Phase 3: User Story 1 - Get a summary with explicit gaps (P1) 🎯 MVP

- [ ] T005 [US1] Add `POST /api/v1/compliance-check/analyze` in `backend/main.py`:
      Repomix conversion (reuse `_convert_upload_to_repomix`) + `generate_project_summary`,
      create a session (T003) storing `code_context`, `summary`; return
      `{session_id, summary, gaps}`
- [ ] T006 [US1] `frontend/app/lib/api.ts`: add `analyzeProject(file, companyName?,
      companyContext?)` posting to `.../analyze`
- [ ] T007 [US1] `frontend/app/page.tsx`: upload now calls `analyzeProject` instead of
      the old direct `runComplianceCheck`; store `{session_id, summary, gaps}` and
      navigate to `/analyse`
- [ ] T008 [US1] `frontend/app/analyse/page.tsx`: new "summary review" section showing
      the summary text and the gap list, rendered before the (existing) results section

**Checkpoint**: uploading a project shows a summary + gaps, nothing else yet.

## Phase 4: User Story 2 - Resolve gaps before running (P1)

- [ ] T009 [US2] Add `POST /api/v1/compliance-check/{session_id}/resolve-gaps` in
      `backend/main.py`: accepts JSON gap answers OR a multipart extra `file`; appends to
      `session.extra_documents`, calls `generate_project_summary` again with
      `code_context + extra_documents`, replaces `session.summary`; returns updated
      `{session_id, summary, gaps}`
- [ ] T010 [US2] `frontend/app/lib/api.ts`: add `resolveGaps(sessionId, answers?, file?)`
- [ ] T011 [US2] `frontend/app/analyse/page.tsx`: per-gap answer input (text) and an
      "upload a document instead" file control; submitting calls `resolveGaps` and
      replaces the displayed summary/gaps with the response
- [ ] T012 [US2] Add `POST /api/v1/compliance-check/{session_id}/run` in `backend/main.py`:
      calls `run_compliance_check_with_index(session.project_index, ...,
      summary_context=session.summary["summary"])` (T004); updates
      `session.unresolved_by_field_id` same as the old endpoint did; returns the
      standard compliance-check response shape
- [ ] T013 [US2] `frontend/app/analyse/page.tsx`: a "Lancer le remplissage" button
      (enabled once the user is done reviewing/resolving gaps) that calls the new `run`
      endpoint and switches the page into the existing results view (spec 003's
      needs_human_input UI reused unchanged for the fallback)
- [ ] T014 [US2] Run `quickstart.md`'s three scenarios (gap resolved by text, gap
      resolved by document, gap left unresolved) against the real API + real `run.py`
      server, per the same live-verification standard used for specs 002/003

**Checkpoint**: full new flow works end-to-end.

## Phase 5: User Story 3 - No unnecessary human involvement (P2)

- [ ] T015 [US3] Run `quickstart.md`'s regression check: a project with no real gaps
      goes straight through `analyze` → (no gap resolution needed) → `run` → a normal
      result, matching spec 002/003 behavior

## Phase 6: Polish

- [ ] T016 [P] Update `README.md`: document the new 3-step flow (`analyze` →
      `resolve-gaps` → `run`), note `/api/v1/compliance-check` (the old single-call
      endpoint) is superseded — decide whether to keep it for backward compat or remove
      it (flag as an open question for the team, don't silently break API consumers)
- [ ] T017 [P] Update `specs/002-rag-code-retrieval/spec.md` / `specs/003-human-in-loop-answers/spec.md`
      cross-references if their Assumptions describe the old single-call flow as current

## Dependencies

Setup → Foundational → US1 (MVP) → US2 (depends on US1's session/summary existing) →
US3 (verification only) → Polish.

## Notes

- `POST /api/v1/compliance-check` (spec 002/003's original single-call endpoint) is not
  deleted by this plan — T016 flags the decision explicitly rather than silently dropping
  API surface a teammate or the frontend's `/compliance` test page might still reference.
