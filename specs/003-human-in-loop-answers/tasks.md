# Tasks: Human-in-the-Loop Answers for Unresolved Questions

**Input**: Design documents from `specs/003-human-in-loop-answers/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested; manual validation via `quickstart.md`.

**Organization**: by user story (US1 = answer + resume, US2 = reject invalid answers).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Add the `uuid` usage needed for session ids (stdlib — no new dependency;
      confirm nothing extra is needed in `backend/requirements.txt`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the session cache both user stories depend on

- [X] T002 Create `backend/session_store.py`: `create_session(project_index,
      system_name, extra_context) -> session_id`, `get_session(session_id) ->
      ComplianceSession | None` (returns None if missing/expired, and refreshes
      `expires_at` on access inline rather than a separate `touch()` — same effect,
      one less function), TTL constant (30 min per research.md)
- [X] T003 In `backend/compliance_agent.py`, `_describe_unresolved_field` now builds
      each `needs_human_input` entry with `field_id`, `type`, `question`, `reasoning`,
      and `options` (for radio/checkbox) per data-model.md `UnresolvedQuestion`
- [X] T004 `run_compliance_check` split into `run_compliance_check` (builds a fresh
      index, returns `(result, project_index)`) + `run_compliance_check_with_index`
      (takes an existing index + optional `human_answers`); when a field's id is in
      `human_answers`, `_human_answer_to_field_answer` builds a synthetic
      `confidence: "human"` answer and `_ask_llm_for_answer` is skipped entirely (FR-004)

**Checkpoint**: session cache exists; `run_compliance_check` can accept pre-supplied
answers, but nothing wires a session id through the API yet.

---

## Phase 3: User Story 1 - Answer and resume without re-uploading (Priority: P1) 🎯 MVP

**Goal**: a user can submit an answer for one unresolved question and get an updated
result, without re-sending the file.

**Independent Test**: per `quickstart.md`'s first scenario.

### Implementation for User Story 1

- [X] T005 [US1] `create_compliance_check` now registers the returned `project_index`
      via `session_store.create_session(...)` and includes `session_id` in the response
- [X] T006 [US1] Added `POST /api/v1/compliance-check/{session_id}/answer` in
      `backend/main.py`: looks up the session (404 if missing/expired), merges answers
      into `session.human_answers`, calls `run_compliance_check_with_index(...)` reusing
      `session.project_index` (no Repomix, no re-embedding), returns the same response
      shape including `session_id`. **Verified with a scripted test** (FastAPI
      `TestClient`, Playwright/LLM mocked out): first call returns options, invalid
      answer → 400 without triggering the mocked resume call, valid case-insensitive
      answer → 200 with merged `human_answers` passed through, unknown session → 404.
- [X] T007 [US1] Added `resumeComplianceCheck(sessionId, answers)` in
      `frontend/app/lib/api.ts`, plus a shared `detailToMessage()` helper since the new
      endpoint's 400 errors are a structured object, not a plain string
- [X] T008 [US1] `frontend/app/analyse/page.tsx` now renders radio buttons for
      `type: "radio"`, checkboxes for `type: "checkbox"`, and a text input only for
      `type: "text"` — no free text for anything with a fixed `options` list (FR-006)
- [X] T009 [US1] Added "Envoyer mes réponses" button: calls `resumeComplianceCheck` with
      only the answers actually filled in, replaces `result` with the response, persists
      it back to `sessionStorage` so a page refresh doesn't lose progress
- [ ] T010 [US1] NOT run — needs a live `ZAI_API_KEY` + real browser session
      (environment limitation noted throughout specs 002/003); verified instead via the
      scripted backend test (T006) plus `tsc`/`eslint`/`next build` all passing for the
      frontend. Should be re-run manually by someone with API access before merge.

**Checkpoint**: the core loop works end-to-end. Shippable increment.

---

## Phase 4: User Story 2 - Reject invalid answers before running automation (Priority: P1)

**Goal**: an invalid multiple-choice answer is rejected fast, with a clear message.

**Independent Test**: per `quickstart.md`'s "reject an invalid answer" scenario.

### Implementation for User Story 2

- [X] T011 [US2] Validation added in `answer_compliance_check`: checks each submitted
      value against `session.unresolved_by_field_id[field_id]["options"]`
      (case-insensitive), returns `400` with the question + valid options before
      `run_compliance_check_with_index` is ever called (SC-002)
- [X] T012 [US2] Verified via the same scripted test (see T006) — invalid answer got
      `400` and the mocked resume function's call count stayed at 1 (only the first
      call), proving Playwright/LLM work is skipped entirely
- [~] T013 [US2] Partially verified: unknown `session_id` → 404 confirmed by script.
      True TTL-expiry (waiting out the 30 min, or a shortened TTL override) NOT
      separately tested — same code path (`get_session` returns None past
      `expires_at`), but the timing itself wasn't exercised

**Checkpoint**: both user stories validated.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T014 [P] Run `quickstart.md`'s regression check (original one-shot flow unmodified)
- [ ] T015 [P] Update `README.md`: document the new resume endpoint, the `session_id`
      field, and the in-memory/single-instance session-cache trade-off (per constitution
      Principle V)
- [ ] T016 Update `specs/001-compliance-check-agent/spec.md` if any of its Assumptions
      about `needs_human_input`'s shape are now stale (it gained `field_id`/`type`/`options`)

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** blocks both stories.
- **US1 (Phase 3)** is the MVP; **US2 (Phase 4)** depends on US1's endpoint existing
  (adds validation to it) — not independent of US1 in this feature, same relationship as
  spec 002's US1/US2.
- **Polish (Phase 5)** after both stories.

## Implementation Strategy

1. Setup + Foundational.
2. US1 → the actual capability ships (answer + resume).
3. US2 → hardens it (reject bad input fast) before calling it done.
4. Polish → docs.
