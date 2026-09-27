# Tasks: Concurrent Analyses (10+ simultaneous users)

**Input**: Design documents from `specs/008-concurrent-analyses/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: pytest unit tests for the new pure logic (queue, pacer, answer reuse) — the
suite added in the review hardening now runs in CI; plus live validation per quickstart.md.

**Organization**: by user story — US1 async submit & follow, US2 many users / queue,
US3 resume through the queue without re-asking, US4 LLM pacing & fewer tokens, US5 more
parallelism.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Add the new limits as env-configurable constants with defaults from research.md
      R9 (`MAX_CONCURRENT_CHECKS=4`, `MAX_ACTIVE_CHECKS_PER_USER=2`,
      `MAX_QUEUED_CHECKS=50`, `MAX_QUEUED_UPLOAD_BYTES=8 GB`) in `backend/job_queue.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T002 `backend/db.py`: `status`/`error`/`started_at`/`finished_at` + idempotent
      `ALTER`s, Python-side defaults, `recover_interrupted_analyses()`,
      `record_analysis_status()`.
- [X] T003 `backend/job_queue.py`: `JobQueue` (FIFO, workers, limits, positions, EMA
      estimate, status recording that can't kill a worker, held uploads always released).
      Also: `stop()` deletes the uploads of jobs still waiting.
- [X] T004 [P] `backend/tests/test_job_queue.py` — 6 tests (order/positions, per-user
      limit, count/bytes bounds, duplicate, failures + cleanup, recorder errors).
- [X] T005 [P] `backend/session_store.py`: `ai_answers`, `busy`, `mark_busy`/`release`;
      test added in `test_session_store.py`.

**Checkpoint**: 24 unit tests passing.

---

## Phase 3: User Story 1 - Submit and follow without waiting on the request (P1) 🎯 MVP

- [X] T006 [US1] `_checked_archive_entries` shared by `_validate_zip` (submission, central
      directory only) and `_write_zip_to_project` (job).
- [X] T007 [US1] `create_compliance_check` → validate, hold upload, create queued
      Analysis, enqueue, **202**.
- [X] T008 [US1] `_run_first_check` job body (extraction, fingerprint, Repomix, check,
      save, session with `ai_answers`). Combined code+PDF fingerprint now uses the PDF's
      SHA-256 (code-only and PDF-only fingerprints unchanged).
- [X] T009 [US1] Lifespan: empty the held-upload dir, recover interrupted analyses, start/
      stop workers, close the shared browser; `/api/v1/analyses` keeps its own guard.
- [X] T010 [P] [US1] `backend/history.py` status fields; `session_id` hidden while active.
- [X] T011 [P] [US1] `frontend/app/lib/api.ts` types (`AnalysisStatus`, `SubmittedAnalysis`).
- [X] T012 [US1] `frontend/app/page.tsx` navigates on 202.
- [X] T013 [US1] `frontend/app/analyse/page.tsx` polling (3 s, keeps polling through a
      network blip while following), status badge, running/failed banners.
- [X] T014 [P] [US1] `frontend/app/historique/page.tsx` status badge.
- [X] T015 [P] [US1] `frontend/app/compliance/page.tsx` redirects to `/analyse?id=`.
- [X] T016 [US1] **Live**: one submission → `202` in 0.12 s, `done` 15 s later. Restart
      (§7): 6 analyses left queued/running, server hard-killed → on restart all 6
      `failed` with "Analyse interrompue par un redémarrage du serveur — merci de la
      relancer.", held-upload dir emptied (6 → 0 files). First attempt found a leak (hard
      kill left the uploads in `%TEMP%`) → fixed with the dedicated, startup-emptied
      `cowsay-uploads/` dir.

---

## Phase 4: User Story 2 - Many users at once: wait your turn (P1)

- [X] T017 [US2] `UserLimitReached` → 429, `QueueFull` → 503, `AlreadyQueued` → 409
      (`_queue_errors_as_http`), checked before anything is written.
- [X] T018 [US2] Queued banner with position + "environ X min".
- [X] T019 [US2] **Live** (`e2e_concurrency.py`, local server):
      - 12 users, small project: 12× `202`, ack max 0.47 s; 13/13 done in 19 s; a 3rd
        submission by one user → `429`.
      - 12 users, real project (88 KB backend code): 13/13 done in 17 s, 0 provider errors.
      - **24 users**, real project: 24× `202`, ack max 0.57 s, positions 0…20 decreasing
        over time; **25/25 done in 77 s**; pacer waited 6 times (up to 42 s at 85.7 k
        tokens in the window); **0 provider `429`, 0 retries**.

---

## Phase 5: User Story 3 - Resume through the same queue, no repeated questions (P1)

- [X] T020 [US3] `answer_field()` helper (human > cached AI answer re-normalized against
      the visible options > new LLM call, cached); wired into the agent loop.
- [X] T021 [P] [US3] `backend/tests/test_answer_reuse.py` — 5 tests.
- [X] T022 [US3] Answer endpoint queued (409 duplicate, busy session, 202); `_run_resume`.
- [X] T023 [US3] Answer form only when not active; resume switches back to polling.
- [X] T024 [US3] **Live** (`e2e_resume.py`, 6 other analyses queued as load): resume →
      `202` at position 3 → running → done; second submission while queued → `409`;
      `session_id` hidden while queued. Round 1: 2 questions / 2 LLM calls; resume: 3
      questions (1 human, 1 answered by the AI in round 1, 1 newly revealed) → **1 LLM
      call, 0 repeated** (SC-006). Per-run cost now logged: "Analysis <id> run finished:
      N questions answered, M asked to the LLM".

---

## Phase 6: User Story 4 - Share the provider quota, fewer tokens (P2)

- [X] T025 [US4] `LlmPacer` in `compliance_agent.py` + `temperature: 0`; logs each wait.
- [X] T026 [P] [US4] `backend/tests/test_llm_pacer.py` — 7 tests (fake clock).
- [X] T027 [US4] Baseline (4000 × 5, temperature 0) on the reference projects.
- [X] T028 [US4] `code_index.py`: `MAX_CHUNK_CHARS = 2000`, `TOP_K_CHUNKS = 4`.
- [X] T029 [US4] **Quality gate passed** (`quality_gate.py`):

      | Project | Prompt tokens / question | Answers & escalations |
      |---|---|---|
      | backend code (88 KB) | 4,858 → 2,238 (−54 %) | identical |
      | loan_model.py only | 430 → 430 (fits in one chunk) | identical |
      | loan_model.py + PDF | 496 → 496 (fits in one chunk) | identical ¹ |
      | same facts inside the 88 KB backend | 3,708 → 1,644 (−56 %) | identical, same confidences |

      ¹ one escalated question's confidence read `low` then `high` with a byte-identical
      prompt — provider nondeterminism even at temperature 0, not the chunking change
      (answer and escalation unchanged). The last row was added because it is the case
      where retrieval actually has to find the facts among unrelated chunks.

---

## Phase 7: User Story 5 - More analyses in parallel on the same server (P3)

- [X] T030 [US5] Shared Chromium (lazy, relaunched if disconnected), one context per check,
      closed in `finally` (tolerates a dead browser); `close_shared_browser()` at shutdown.
      Side effect measured: a small check went from ~10 s to ~3.5 s (no browser launch).
- [X] T031 [P] [US5] Lock around the lazy embedding-model init.
- [X] T032 [US5] **Live** in Docker `--cpus 2 --memory 8g`, running as `app`: 8 analyses of
      a 90 KB project → **4 running at the same time**, 8/8 done in 69 s, container memory
      peak **982 MiB** (idle 118 MiB), worst `/health` latency 215 ms.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T033 [P] `README.md`: async flow, statuses, endpoints (202/409/429/503), env vars,
      pacing, chunk settings + 128-token finding, 1-task constraint, Status section.
- [X] T034 Full local gate: `pytest` (38 passed), `npm run lint`, `npx tsc --noEmit`,
      `npm run build` — all clean.
- [X] T035 spec.md Status updated; results recorded here.

**Not verified**: the frontend's visual rendering in a real browser (no browser tool in
this environment) — the polling/banners are checked by types, lint and build only.

---

## Dependencies & Execution Order

- Setup (T001) → Foundational (T002–T005) blocks every story.
- US1 (T006–T016) is the MVP and a prerequisite for US2 and US3.
- US2 (T017–T019) and US3 (T020–T024) are independent of each other after US1.
- US4 (T025–T029): the T027 baseline ran **before** T028.
- US5 (T030–T032) after US1 (lifespan hooks).
- Polish last.
