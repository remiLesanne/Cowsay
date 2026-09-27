# Implementation Plan: Concurrent Analyses (10+ simultaneous users)

**Branch**: `feature/concurrent-analyses` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-concurrent-analyses/spec.md`

## Summary

Turn a compliance check from one long synchronous request into a queued job. Submitting
(or resuming with human answers) validates the input, creates/updates the `Analysis` row
with status `queued`, enqueues an in-process job and returns `202` at once; a fixed pool
of workers (`MAX_CONCURRENT_CHECKS`, default 4) runs jobs FIFO, and the frontend polls the
analysis until it is `done` or `failed`, showing queue position and an estimated wait.
Around that: one shared Chromium with a context per check (more checks in parallel on the
same 2 vCPU / 8 GB task), a process-wide pacer that keeps LLM calls under the provider's
per-minute quotas, reuse of the AI's earlier answers on resume, and smaller prompts
(2,000-char chunks, top 4) — together the token budget, not the server, stays the only
ceiling, and it's spent ~2× more efficiently. See [research.md](research.md) for the
measurements behind each decision.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript / Next.js 16 (frontend) — unchanged.

**Primary Dependencies**: no new dependency. asyncio (queue, workers, pacing), existing
Playwright (shared browser + contexts), SQLAlchemy (status columns), httpx.

**Storage**: PostgreSQL `analyses` gains `status`, `error`, `started_at`, `finished_at`
(idempotent `ALTER TABLE` at startup, like `pdf_warning`). Uploads waiting in the queue
are held as private temp files, deleted after their job (never stored durably — spec 005
FR-009 / spec FR-018). Queue, sessions and AI-answer memory stay in process memory.

**Testing**: pytest unit tests (queue, limits, restart recovery, pacer with a fake clock,
AI-answer reuse helpers) + live validation per [quickstart.md](quickstart.md) (12
concurrent users, resume, token/quality comparison, Docker parallelism, restart).

**Target Platform**: existing single ECS Fargate task (2 vCPU / 8 GB) + Vercel frontend.

**Project Type**: web-service + web-app (existing structure).

**Performance Goals**: acknowledge a submission in < 5 s; 12 small analyses submitted
together all done within 10 min on the free Mistral tier; ≥ 4 analyses in progress at
once; ≥ 30 % fewer prompt tokens per question.

**Constraints**: Mistral free tier 100 req/min, 100 k tokens/min (measured, shared with any
local developer using the same key); single backend instance (in-memory queue/sessions —
the service must stay at 1 task); Fargate 20 GB ephemeral storage (bounds held uploads).

**Scale/Scope**: 10–20 simultaneous users (a class / demo), up to 50 waiting analyses.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (drive the real tool)**: PASS — every check still drives the real
  checker page; contexts in a shared browser are isolated (own cookies/storage), so one
  user's answers can't leak into another's form.
- **Principle II (no silent guessing)**: PASS — reused AI answers are the same answers
  already shown to the user (still escalated if low confidence); a failed job is shown as
  failed with its reason instead of disappearing; smaller prompts are gated on identical
  answers/escalations on reference projects (R5), with a documented fallback.
- **Principle III (spec-driven)**: PASS — spec, this plan, tasks.
- **Principle IV (production-shaped)**: PASS — bounded queue, per-user limit, bounded
  on-disk held uploads, restart recovery, provider quota respected by design rather than
  by retry storms; all limits are env-configurable and documented.
- **Principle V (README current)**: README must document the async flow, statuses,
  limits/env vars and the "keep 1 ECS task" constraint — tracked as a task.

Post-design re-check (after research/data-model/contracts): unchanged, PASS. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/008-concurrent-analyses/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0: measurements + decisions R1–R9
├── data-model.md        # Phase 1: Analysis status columns, job, session additions
├── contracts/api.md     # Phase 1: 202 responses, new errors, status fields
├── quickstart.md        # Phase 1: validation scenarios
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── job_queue.py          # NEW: FIFO queue + MAX_CONCURRENT_CHECKS workers started in the
│                         # app lifespan; per-user / queue-size / held-bytes limits;
│                         # positions; duration EMA for estimates; marks the Analysis
│                         # running/done/failed; always deletes held uploads.
├── main.py               # compliance-check + answer endpoints: validate, create/update
│                         # Analysis (queued), enqueue, return 202; zip pre-validation
│                         # without extraction; job bodies (first run / resume) moved into
│                         # functions the queue calls; lifespan starts/stops workers and
│                         # the shared browser; /analyses keeps its own small guard.
├── compliance_agent.py   # shared browser (lazy, relaunch on disconnect, context per
│                         # check); LLM pacer (sliding window, limits from headers);
│                         # temperature 0; reuse of previous AI answers.
├── code_index.py         # MAX_CHUNK_CHARS 2000, TOP_K_CHUNKS 4 (quality-gated, R5);
│                         # lock around lazy embedding-model init.
├── session_store.py      # ai_answers + busy flag; busy sessions never expire/purge.
├── db.py                 # status/error/started_at/finished_at columns + ALTERs; startup
│                         # recovery of queued/running rows.
├── history.py            # status, error, queue position/estimate in detail; status in
│                         # list; session_id only when done.
└── tests/                # NEW tests: test_job_queue.py, test_llm_pacer.py,
                          # test_answer_reuse.py

frontend/app/
├── lib/api.ts            # 202 response types; status fields on AnalysisResult/Summary
├── page.tsx              # navigate as soon as the 202 arrives (no 2-min wait text)
├── analyse/page.tsx      # poll every 3 s while queued/running; queue/running/failed
│                         # banners; answer form only when done; resume → back to polling
├── historique/page.tsx   # status badge (En attente / En cours / Complété / Incomplet / Échec)
└── compliance/page.tsx   # test page: redirect to /analyse?id= after submit
```

**Structure Decision**: one new backend module (`job_queue.py`) in the repo's
one-module-per-concern style; everything else extends existing modules. No new service,
broker or dependency (R2).

## Complexity Tracking

No constitution violations — table not needed.
