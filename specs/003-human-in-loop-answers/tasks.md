# Tasks: Human-in-the-Loop Answers for Unresolved Questions

**Input**: Design documents from `specs/003-human-in-loop-answers/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: not requested; manual validation via `quickstart.md`.

**Organization**: by user story (US1 = answer + resume, US2 = reject invalid answers).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Add the `uuid` usage needed for session ids (stdlib — no new dependency;
      confirm nothing extra is needed in `backend/requirements.txt`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the session cache both user stories depend on

- [ ] T002 Create `backend/session_store.py`: `create_session(project_index) ->
      session_id`, `get_session(session_id) -> ComplianceSession | None` (returns None if
      missing or past `expires_at`, per data-model.md Validation rules), `touch(session_id)`
      to refresh `expires_at` on access, TTL constant (30 min per research.md)
- [ ] T003 In `backend/compliance_agent.py`, extend the field-scanning JS/Python path so
      each `needs_human_input` entry also carries `field_id`, `type`, and `options` (for
      radio/checkbox) per data-model.md `UnresolvedQuestion`
- [ ] T004 In `backend/compliance_agent.py`, add a `human_answers: dict[str, str | list[str]]
      | None` parameter to `run_compliance_check`; when the loop encounters a field whose
      id is in `human_answers`, apply that value directly via `_apply_answer` and record it
      as answered WITHOUT calling `_ask_llm_for_answer` (FR-004)

**Checkpoint**: session cache exists; `run_compliance_check` can accept pre-supplied
answers, but nothing wires a session id through the API yet.

---

## Phase 3: User Story 1 - Answer and resume without re-uploading (Priority: P1) 🎯 MVP

**Goal**: a user can submit an answer for one unresolved question and get an updated
result, without re-sending the file.

**Independent Test**: per `quickstart.md`'s first scenario.

### Implementation for User Story 1

- [ ] T005 [US1] In `backend/main.py`'s `create_compliance_check`, after building the
      `ProjectIndex`, register it via `session_store.create_session(...)` and include the
      returned `session_id` in the response (alongside the existing fields)
- [ ] T006 [US1] Add `POST /api/v1/compliance-check/{session_id}/answer` in
      `backend/main.py`: look up the session (404 if missing/expired, data-model.md),
      merge the submitted answers into the session's accumulated `human_answers`, call
      `run_compliance_check(..., human_answers=session.human_answers)` reusing
      `session.project_index` (no Repomix, no re-embedding), return the same response
      shape as the original endpoint including the same `session_id`
- [ ] T007 [US1] In `frontend/app/lib/api.ts`, add `resumeComplianceCheck(sessionId,
      answers)` posting to the new endpoint
- [ ] T008 [US1] In `frontend/app/analyse/page.tsx`, render each `needs_human_input` item:
      radio buttons for `type: "radio"` (single choice from `options`), checkboxes for
      `type: "checkbox"` (multi-select from `options`), a text input for `type: "text"` —
      per FR-006/SC-003 no free text for a field that has `options`
- [ ] T009 [US1] Add a "Submit answers" action on `/analyse` that calls
      `resumeComplianceCheck` with the currently-filled-in answers, replaces the displayed
      result with the response, and clears/updates the unresolved-questions list
- [ ] T010 [US1] Run `quickstart.md`'s "answer an unresolved question" scenario manually;
      confirm no file re-upload occurs and the previously-unresolved question disappears
      from the new result

**Checkpoint**: the core loop works end-to-end. Shippable increment.

---

## Phase 4: User Story 2 - Reject invalid answers before running automation (Priority: P1)

**Goal**: an invalid multiple-choice answer is rejected fast, with a clear message.

**Independent Test**: per `quickstart.md`'s "reject an invalid answer" scenario.

### Implementation for User Story 2

- [ ] T011 [US2] In `backend/main.py`'s new answer endpoint, before calling
      `run_compliance_check`, validate each submitted answer against the session's cached
      `UnresolvedQuestion.options` for that `field_id` (case-insensitive compare, matching
      `compliance_agent.py`'s existing `_strip_html(...).strip().lower()` normalization
      per data-model.md); on mismatch return `400` with the question and valid options,
      WITHOUT calling `run_compliance_check` at all (SC-002)
- [ ] T012 [US2] Run `quickstart.md`'s invalid-answer curl scenario; confirm `400` and no
      multi-second wait (Playwright never launches)
- [ ] T013 [US2] Run `quickstart.md`'s expired-session scenario (or a short TTL override
      for testing); confirm a clear `404`-style error, not a silent wrong/empty result

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
