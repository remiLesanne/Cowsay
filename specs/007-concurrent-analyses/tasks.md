# Tasks: Concurrent Analyses (10+ simultaneous users)

**Input**: Design documents from `specs/007-concurrent-analyses/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: pytest unit tests for the new pure logic (queue, pacer, answer reuse) — the
suite added in the review hardening now runs in CI; plus live validation per quickstart.md.

**Organization**: by user story — US1 async submit & follow, US2 many users / queue,
US3 resume through the queue without re-asking, US4 LLM pacing & fewer tokens, US5 more
parallelism.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Add the new limits as env-configurable constants with defaults from research.md
      R9 (`MAX_CONCURRENT_CHECKS=4`, `MAX_ACTIVE_CHECKS_PER_USER=2`,
      `MAX_QUEUED_CHECKS=50`, `MAX_QUEUED_UPLOAD_BYTES=8 GB`) in `backend/job_queue.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: persisted statuses, the queue itself, and session flags every story builds on.

- [ ] T002 `backend/db.py`: add `status VARCHAR(16) NOT NULL DEFAULT 'done'`, `error TEXT
      NULL`, `started_at TIMESTAMPTZ NULL`, `finished_at TIMESTAMPTZ NULL` to `Analysis`
      (+ idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `init_db`); Python-side
      defaults `results_text=''`, `is_complete=False`, `content_fingerprint=''`; add
      `recover_interrupted_analyses()` marking `queued`/`running` rows `failed` with
      "Analyse interrompue par un redémarrage du serveur — merci de la relancer." (FR-015)
- [ ] T003 `backend/job_queue.py`: `JobQueue` — FIFO of jobs, `start(n)` spawns n worker
      tasks, `stop()`; `enqueue(job)` raising `QueueFull` / `UserLimitReached` /
      `AlreadyQueued` (per analysis); `position(analysis_id)` (1-based, 0 if running,
      None otherwise); `estimate(position)` = `ceil(position / workers) × EMA duration`
      (initial 60 s); worker marks the Analysis `running` (+`started_at`, clears `error`),
      runs the job's coroutine, then `done`/`failed` (+`finished_at`, `error` from
      `HTTPException.detail` or a generic message, traceback logged); always releases held
      upload bytes and deletes the temp file (FR-005, FR-007, FR-014, FR-018)
- [ ] T004 [P] `backend/tests/test_job_queue.py`: FIFO order, positions decreasing as jobs
      finish, per-user limit, queue-size and held-bytes limits, duplicate job for the same
      analysis refused, failing job → `failed` with its detail and slot released, temp file
      deleted on success and failure (DB writes stubbed)
- [ ] T005 [P] `backend/session_store.py`: `ComplianceSession.ai_answers: dict` and
      `busy: bool`; `_purge_expired` and `get_session` never expire a busy session; helper
      to set/clear busy that restarts the TTL on clear (FR-009); extend
      `backend/tests/test_session_store.py`

**Checkpoint**: statuses persist, a queue with limits exists and is unit-tested.

---

## Phase 3: User Story 1 - Submit and follow without waiting on the request (P1) 🎯 MVP

**Goal**: submitting returns in seconds; the analysis page follows the run to its result.

**Independent Test**: quickstart.md §2 (and §7 restart).

- [ ] T006 [US1] `backend/main.py`: `_validate_zip(archive)` — same traversal / ignored-dir
      / file-count / uncompressed-size checks as `_write_zip_to_project`, from the central
      directory only, no extraction; used at submission
- [ ] T007 [US1] `backend/main.py` `create_compliance_check`: validate (files, PDF, zip),
      write the upload to a private temp file, create the `Analysis` (`status='queued'`,
      `pdf_warning`, filename, company), enqueue a `first_run` job, return **202** per
      contracts/api.md (`analysis_id`, `status`, `queue_position`,
      `estimated_wait_seconds`, `filename`, `pdf_warning`)
- [ ] T008 [US1] `backend/main.py`: first-run job body — extract the temp upload, fingerprint,
      Repomix, combine with PDF text, `run_compliance_check`, save results + fingerprint on
      the Analysis, create the session (with `ai_answers` from the run)
- [ ] T009 [US1] `backend/main.py` lifespan: `recover_interrupted_analyses()`, start the
      queue workers; on shutdown stop workers; `/api/v1/analyses` keeps its own small
      concurrency guard (the old `_check_slot`, renamed) — adapt
      `backend/tests/test_uploads.py` accordingly
- [ ] T010 [P] [US1] `backend/history.py`: detail adds `status`, `error`, `queue_position`,
      `estimated_wait_seconds`, `started_at`, `finished_at`; `session_id` only when
      `status == 'done'`; list items add `status`
- [ ] T011 [P] [US1] `frontend/app/lib/api.ts`: `AnalysisStatus` type, status fields on
      `AnalysisResult`/`AnalysisSummary`, `runComplianceCheck` returns the 202 body
- [ ] T012 [US1] `frontend/app/page.tsx`: navigate to `/analyse?id=` as soon as the 202
      arrives; button text "Envoi…" instead of "jusqu’à 2 min"
- [ ] T013 [US1] `frontend/app/analyse/page.tsx`: poll `getAnalysis` every 3 s while
      `queued`/`running` (stop on `done`/`failed`/unmount); "Analyse en cours…" banner;
      failed → rose banner with `error` + link "Relancer une analyse" (FR-016)
- [ ] T014 [P] [US1] `frontend/app/historique/page.tsx`: status badge — En attente / En cours
      / Échec, else Complété / Incomplet (FR-017)
- [ ] T015 [P] [US1] `frontend/app/compliance/page.tsx`: after submit, go to `/analyse?id=`
- [ ] T016 [US1] Live: quickstart.md §2 and §7 (restart marks queued/running as failed, no
      leftover temp files)

**Checkpoint**: MVP — no request-timeout dependency, results followed by polling.

---

## Phase 4: User Story 2 - Many users at once: wait your turn (P1)

**Goal**: every valid submission is accepted; waiting users see position and estimate.

**Independent Test**: quickstart.md §3.

- [ ] T017 [US2] `backend/main.py`: map `UserLimitReached` → 429 and `QueueFull` → 503 with
      the contracts/api.md messages, raised before the Analysis row is created
- [ ] T018 [US2] `frontend/app/analyse/page.tsx`: queued banner "En file d’attente —
      position N · environ X min" from `queue_position` / `estimated_wait_seconds`
- [ ] T019 [US2] Live: quickstart.md §3 — 12 accounts submit concurrently; record
      acknowledgment times, positions over time, total duration, 429s in the log

**Checkpoint**: 12 simultaneous users all served, none refused for load.

---

## Phase 5: User Story 3 - Resume through the same queue, no repeated questions (P1)

**Goal**: answering pending questions is queued like a submission and only asks the AI
about new questions.

**Independent Test**: quickstart.md §4.

- [ ] T020 [US3] `backend/compliance_agent.py`: `run_compliance_check_with_index(...,
      ai_answers)` — for a field with no human answer but an entry in `ai_answers`, reuse
      it (source `ai`, no LLM call); store every new AI answer into `ai_answers`; the
      decision lives in a small pure helper so it is unit-testable (FR-010)
- [ ] T021 [P] [US3] `backend/tests/test_answer_reuse.py`: human > cached AI > ask LLM;
      new answers cached; cached low-confidence answers still escalated
- [ ] T022 [US3] `backend/main.py` answer endpoint: validate options (unchanged), refuse if a
      job for this analysis is queued/running (409), mark session busy, set Analysis
      `queued`, enqueue a `resume` job, return 202; resume job body runs
      `run_compliance_check_with_index` with `human_answers` + `ai_answers`, saves results,
      clears busy (FR-008, FR-009)
- [ ] T023 [US3] `frontend/app/analyse/page.tsx`: answer form only when `status == 'done'`;
      after submitting, switch to polling
- [ ] T024 [US3] Live: quickstart.md §4 — count LLM calls on the resume vs newly revealed
      fields; second submission while queued → 409

**Checkpoint**: human-in-the-loop works under load and costs no repeated tokens.

---

## Phase 6: User Story 4 - Share the provider quota, fewer tokens (P2)

**Goal**: no 429 storms; ≥ 30 % fewer prompt tokens with identical answers.

**Independent Test**: quickstart.md §3 (no 429) and §5.

- [ ] T025 [US4] `backend/compliance_agent.py`: `LlmPacer` — sliding 60 s window over
      requests and tokens, FIFO waiting under an `asyncio.Lock`, 90 % of limits, reserve
      `len(prompt) // 3 + 300` then settle with `usage.total_tokens`, limits updated from
      `x-ratelimit-limit-req-minute` / `x-ratelimit-limit-tokens-minute`; wired into
      `_post_to_llm`; add `"temperature": 0` to the request body (research.md R4, R5)
- [ ] T026 [P] [US4] `backend/tests/test_llm_pacer.py`: with an injected clock/sleep —
      waits when the token or request budget is full, releases as the window slides,
      settles estimates, adopts header limits, preserves FIFO order
- [ ] T027 [US4] Quality baseline: run the 3 reference projects (research.md R5) with the
      current chunk settings at temperature 0, record prompt tokens per question and every
      answer/escalation (scratchpad script)
- [ ] T028 [US4] `backend/code_index.py`: `MAX_CHUNK_CHARS = 2000`, `TOP_K_CHUNKS = 4`
- [ ] T029 [US4] Quality gate: re-run T027; require ≥ 30 % fewer prompt tokens and identical
      answers/escalations; otherwise apply the R5 fallback (`TOP_K_CHUNKS = 3`, 4000-char
      chunks) and re-run; record the numbers in this file

**Checkpoint**: quota shared gracefully, token use reduced without quality loss.

---

## Phase 7: User Story 5 - More analyses in parallel on the same server (P3)

**Goal**: ≥ 4 analyses in progress at once on 2 vCPU / 8 GB.

**Independent Test**: quickstart.md §6.

- [ ] T030 [US5] `backend/compliance_agent.py`: one shared Chromium (lazy launch under an
      `asyncio.Lock`, relaunch if `not browser.is_connected()`), `browser.new_context()`
      per check closed in `finally`; `close_shared_browser()` called from the lifespan
      shutdown in `backend/main.py`
- [ ] T031 [P] [US5] `backend/code_index.py`: `threading.Lock` around the lazy embedding
      model init
- [ ] T032 [US5] Live: quickstart.md §6 in Docker with `--cpus 2 --memory 8g` — 4 running at
      once, memory headroom, `/health` responsive

**Checkpoint**: parallelism doubled on the same hardware.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T033 [P] `README.md`: async flow + statuses, new/changed endpoints (202, 409, 429, 503),
      env vars (`MAX_CONCURRENT_CHECKS`, `MAX_ACTIVE_CHECKS_PER_USER`, `MAX_QUEUED_CHECKS`,
      `MAX_QUEUED_UPLOAD_BYTES`), pacing, chunk settings + the 128-token embedding finding,
      "keep the ECS service at exactly 1 task", Status section
- [ ] T034 Full local gate: `pytest`, `npm run lint`, `npx tsc --noEmit`, `npm run build`
- [ ] T035 Mark spec.md Status and record live results next to each task here

---

## Dependencies & Execution Order

- Setup (T001) → Foundational (T002–T005) blocks every story.
- US1 (T006–T016) is the MVP and a prerequisite for US2 and US3 (they reuse its async
  endpoints, polling UI and job bodies).
- US2 (T017–T019) and US3 (T020–T024) are independent of each other after US1.
- US4 (T025–T029) only touches `compliance_agent.py` / `code_index.py`; it can start
  after Foundational, but T025 and T020/T030 edit the same file → do them sequentially.
  The T027 baseline must run **before** T028.
- US5 (T030–T032) after US1 (lifespan hooks) — same-file caution with US3/US4.
- Polish last.

### Parallel opportunities

- T004 ∥ T005 (different files); T010 ∥ T011 ∥ T014 ∥ T015; T021 ∥ T022 (test vs
  endpoint); T026 ∥ T027; T031 ∥ T030.

## Implementation Strategy

1. Foundational + US1 → no more request timeouts; a single user's experience is the same
   result, delivered asynchronously. Shippable.
2. US2 → the 10+ users requirement itself (queue, positions, limits).
3. US3 → resumes under load, cheaper.
4. US4 → throughput within the free quota (the real ceiling).
5. US5 → shorter waits when the server, not the quota, is the bottleneck.
6. Polish → README, full gate.
