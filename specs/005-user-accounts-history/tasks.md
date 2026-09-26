# Tasks: User Accounts and Per-User Analysis History

**Input**: Design documents from `specs/005-user-accounts-history/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: no automated test tasks — team decision (manual validation via
[quickstart.md](quickstart.md)); each story ends with its manual checkpoint.

**Before writing frontend code**: read the relevant guide in
`frontend/node_modules/next/dist/docs/` (Next.js 16 has breaking changes — see
`frontend/AGENTS.md`), notably for `useSearchParams` and client navigation.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Add `sqlalchemy>=2`, `psycopg[binary]>=3`, `pwdlib[argon2]`, `pyjwt`, `email-validator` to `backend/requirements.txt` and install them in `backend/.venv`
- [X] T002 [P] In `backend/.env.example`, replace the locally-edited `DATABASE_URL` line with the placeholder `DATABASE_URL=postgresql+psycopg://cowsay:CHANGE_ME@localhost:5432/cowsay` and add `JWT_SECRET=CHANGE_ME` (never a real secret in this tracked file); remind the user to add a real `JWT_SECRET` to `backend/.env`

---

## Phase 2: Foundational (blocks all stories)

- [X] T003 Create `backend/db.py`: engine + `SessionLocal` from `DATABASE_URL` (clear error if missing), declarative `Base`, `get_db` FastAPI dependency, `init_db()` calling `Base.metadata.create_all`; models per data-model.md — `User` (`id` UUID PK, `email` unique "stored lower-cased and trimmed", `password_hash`, `created_at`) and `Analysis` (`id` UUID PK, `user_id` FK→users indexed, `filename`, `content_fingerprint` char(64) indexed, `company_name` nullable, `results_text`, `is_complete`, `question_details` JSONB, `needs_human_input` JSONB, `created_at`, `updated_at`)
- [X] T004 Call `init_db()` at startup in `backend/main.py` (FastAPI lifespan) so tables exist on first run
- [X] T005 Create `backend/auth.py`: argon2 hashing via `pwdlib`, `create_access_token(user_id)` (HS256, 24h, `JWT_SECRET` from env), `get_current_user` dependency reading `Authorization: Bearer` → `401` on missing/invalid/expired token or unknown user

**Checkpoint**: backend starts, `\dt` in psql shows `users` and `analyses`.

---

## Phase 3: User Story 1 — Create an account and log in (P1) 🎯 MVP

**Goal**: register / login / logout / current user, and a logged-out visitor is sent to `/login`.
**Independent test**: quickstart scenarios 1-3 and 8.

- [X] T006 [US1] Add an `APIRouter` in `backend/auth.py` per contracts/api.md: `POST /api/v1/auth/register` (`EmailStr`, password "at least 8 characters", `409` if email exists case-insensitively, returns token + user, status 201), `POST /api/v1/auth/login` (one generic `401` message for unknown email or wrong password), `GET /api/v1/auth/me`; include it in `backend/main.py`
- [X] T007 [P] [US1] In `frontend/app/lib/api.ts`: token get/set/clear in `localStorage` (guarded for SSR), an `authFetch` helper adding the bearer header and, on `401`, clearing the token and redirecting to `/login`; `register`, `login`, `logout`, `getMe` functions
- [X] T008 [P] [US1] Create `frontend/app/components/useRequireAuth.ts` (client hook: no token or `/auth/me` fails → `router.replace('/login')`; returns the current user) and `frontend/app/components/AppHeader.tsx` (logo linking home, "Mes analyses" link, user email, "Se déconnecter" button → clear token → `/login`), reusing the existing header styling from `frontend/app/page.tsx`
- [X] T009 [P] [US1] Create `frontend/app/login/page.tsx` and `frontend/app/register/page.tsx` (email + password forms in the existing visual style, French messages, link between the two, redirect to `/` on success)
- [X] T010 [US1] Guard `frontend/app/page.tsx` with `useRequireAuth` and replace its inline header with `AppHeader`

**Checkpoint**: quickstart 1-3, 8 pass; the upload still fails until US2 (401), expected.

---

## Phase 4: User Story 2 — Saved compliance check (P1)

**Goal**: authenticated check + resume, persisted as one analysis row, per-question detail returned, text-answer bug fixed.
**Independent test**: quickstart scenarios 4-5 and the curl `401` check.

- [X] T011 [P] [US2] In `backend/compliance_agent.py`, build `question_details` in `run_compliance_check_with_index` for every processed field (`field_id`, `type`, `question` stripped of HTML, `answer` = selected list for radio/checkbox or text, `reasoning`, `confidence`, `source` `"ai"`/`"human"`) and add it to the returned dict
- [X] T012 [P] [US2] In `backend/session_store.py`, add `user_id` and `analysis_id` to `ComplianceSession` and `create_session`, plus `find_session_id_by_analysis(analysis_id)` (skips expired sessions)
- [X] T013 [US2] In `backend/main.py`, compute the content fingerprint in `_convert_upload_to_repomix` (SHA-256 over sorted relative path + bytes of the extracted, non-ignored files; single file: name + bytes) and return it
- [X] T014 [US2] In `backend/main.py`, require `get_current_user` on `POST /api/v1/compliance-check`; after a successful run insert an `Analysis` row (fields per data-model.md), create the session with `user_id`/`analysis_id`, and return `analysis_id` + `question_details` (contracts/api.md)
- [X] T015 [US2] In `backend/main.py` `answer_compliance_check`: require `get_current_user`; treat a session owned by another user as `404`; **fix the bug** — validate options only for radio/checkbox but store every answer for a known pending field (text included) in `session.human_answers`; after a successful run update the same `Analysis` row (`results_text`, `is_complete`, `question_details`, `needs_human_input`, `updated_at`)
- [X] T016 [US2] In `frontend/app/lib/api.ts`, make `runComplianceCheck` and `resumeComplianceCheck` use `authFetch`; add `getAnalysis(id)` for `GET /api/v1/history/{id}` (implemented in US3, used here to load the result page)
- [X] T017 [US2] In `frontend/app/page.tsx`, after a successful check navigate to `/analyse?id=<analysis_id>` instead of the `sessionStorage` hand-off
- [X] T018 [US2] Rework `frontend/app/analyse/page.tsx`: guarded + `AppHeader`; read `id` from the URL (`useSearchParams`, wrapped in `Suspense` per Next 16 docs) and load via `getAnalysis`; add a per-question table (question, answer, reasoning, source badge IA/humain); pending-question form only when `session_id` is present, otherwise a message "session expirée — relancez une analyse en renvoyant le fichier"; after a resume, refresh from the response
- [X] T019 [P] [US2] Make `frontend/app/compliance/page.tsx` use the authenticated `runComplianceCheck` (401 → login) — no other change

**Checkpoint**: quickstart 4-5 pass; `SELECT filename, is_complete FROM analyses;` shows one row per check, updated on resume.

---

## Phase 5: User Story 3 — Mes analyses (P2)

**Goal**: list and reopen own analyses from the database.
**Independent test**: quickstart scenarios 6-7.

- [X] T020 [US3] Create `backend/history.py` router: `GET /api/v1/history` (current user's analyses, `created_at` desc, summary fields) and `GET /api/v1/history/{analysis_id}` (full record filtered on `user_id` → `404` otherwise; includes `session_id` only if `find_session_id_by_analysis` finds a live session); include it in `backend/main.py`
- [X] T021 [US3] Create `frontend/app/historique/page.tsx`: guarded + `AppHeader`, list newest first (file name, date, company, complete/incomplete badge) linking to `/analyse?id=`, empty state with a link to start an analysis

**Checkpoint**: quickstart 6-7 pass (two accounts, no cross visibility).

---

## Phase 6: Polish & Cross-Cutting

- [ ] T022 Run all [quickstart.md](quickstart.md) scenarios end-to-end, including the backend-restart persistence check; `npx tsc --noEmit`, `npm run lint`, `npm run build` in `frontend/`
- [ ] T023 [P] Update `README.md`: auth + history endpoints, new env vars (`DATABASE_URL`, `JWT_SECRET`), local Postgres setup, accepted trade-offs (client-side logout, localStorage token, `create_all`), move "No database or auth" from "Not done yet" to "Done", note the text-answer fix; keep it dense (constitution V)
- [ ] T024 [P] Update `specs/003-human-in-loop-answers/spec.md` Status/notes to reference the text-answer fix done in spec 005

---

## Dependencies & Execution Order

- Setup (T001-T002) → Foundational (T003-T005) → US1 → US2 → US3 → Polish.
- US2 needs US1's auth (endpoints require a user) and the frontend guard/header.
- US3's backend detail route (T020) is what US2's result page loads (T016/T018): implement T020 right after T015 if validating US2 in the browser before US3's list page.

## Parallel Opportunities

- T002 alongside T001; T007/T008/T009 (distinct frontend files) once T006 exists.
- T011 and T012 (different backend files) before T013-T015.

## Implementation Strategy

1. Setup + Foundational, then US1 → demoable login (MVP).
2. US2 (+ T020) → saved checks; US3 → history page.
3. Polish → full quickstart run, README. One commit per phase on
   `feature/user-accounts-history`; nothing merged to `main` without the user's OK
   (a push to `main` triggers the AWS deploy).
