# Cowsay — EU AI Act Compliance Checker

**Goal (school project, EPF 5A):** given a codebase and/or a PDF describing an AI
system (+ optional company info), automatically determine whether that project
complies with the EU AI Act.
The app fills the official Future-of-Life-Institute checker
(https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/)
using facts extracted from the code, returns its real recommendation, and
flags any question the AI couldn't answer so a human can fill the gap.
Full brief: not versioned here — ask the team / check project chat if unsure.

Rubric constraints that shape decisions: must have a generative-AI/agentic
component; if using a coding harness (Claude Code etc.) must also use an
agentic framework to avoid "vibe coding"; team works agile (tickets, PRs,
acceptance criteria).

## Architecture

```
Next.js frontend (frontend/)  --HTTP-->  FastAPI backend (backend/)
                                             |
             /api/v1/analyses                       (Repomix only: code -> AI-readable text)
             /api/v1/compliance-check                (queue a check -> 202; Repomix + Playwright agent run from the queue)
             /api/v1/compliance-check/{id}/answer    (queue a resume with human answers for unresolved questions)
             /api/v1/auth/*, /api/v1/history         (accounts + saved analyses, PostgreSQL — spec 005)
```

**Accounts & history (spec 005)**: running/resuming a check requires a
logged-in user (email + password, argon2, 24h JWT bearer — `backend/auth.py`).
Every check is saved as one `analyses` row in PostgreSQL, created at submission
(`backend/db.py`, tables created at startup — no migrations yet), updated in
place on each resume round: file name, content fingerprint (SHA-256 of the
extracted files — **the code itself is never stored**), company, verdict,
per-question detail (question/answer/reasoning/source AI or human), pending
questions. Users only ever see/resume their own (others' → `404`).
Trade-offs: logout is client-side (token discarded, still valid until
expiry), token in `localStorage` (cross-origin front/back rules out cookies
without HTTPS on the backend). See `specs/005-user-accounts-history/research.md`.

**Concurrent users (spec 007)**: a check is a queued job, not one long
request. Submitting (or answering pending questions) validates everything,
creates/updates the analysis with `status: queued` and returns `202` at once;
`backend/job_queue.py` runs jobs FIFO with `MAX_CONCURRENT_CHECKS` (default 4)
workers, and the frontend polls `GET /history/{id}` every 3 s, showing queue
position + estimated wait (`queued → running → done | failed`). Nobody is
refused because of load — except per-user (`MAX_ACTIVE_CHECKS_PER_USER`,
default 2 → `429`) and when the bounded queue is full (`MAX_QUEUED_CHECKS`
50 / `MAX_QUEUED_UPLOAD_BYTES` 8 GB → `503`). Uploads wait as private temp
files in `$TMPDIR/cowsay-uploads/` (deleted after the job; the folder is
emptied at startup). On startup, analyses left queued/running by a previous
process are marked failed ("interrompue par un redémarrage"). The **real
ceiling is Mistral's free quota** (measured: 100 req/min, 100 k tokens/min),
not the server: `LlmPacer` (`compliance_agent.py`) keeps every LLM call of the
process under 90 % of it (sliding 60 s window, limits read from
`x-ratelimit-limit-*` headers, so a paid key is used fully without code
changes) — calls wait instead of getting `429`s. Tokens per question were
halved (4 × 2,000-char chunks instead of 5 × 4,000; the embedding tokenizer
truncates at 128 tokens anyway), answers are requested at `temperature: 0`,
and a resume reuses the AI's earlier answers (only newly revealed questions
go to the LLM). One shared Chromium, a fresh context per check. Live-verified
(spec 007 `tasks.md`): 24 users at once → 24× `202` in < 0.6 s, 25/25 done in
77 s, 0 provider `429`; 4 checks running at once in a `--cpus 2 --memory 8g`
container at < 1 GB. **The ECS service must stay at exactly 1 task**: queue,
sessions and AI-answer memory live in that process.

`POST /api/v1/compliance-check` runs the check flow (specs 002/003): upload
(code file/zip and/or a PDF — spec 006, see below) → Repomix →
`backend/compliance_agent.py` drives a headless Chromium through
the official checker's form (a dynamic branching questionnaire — WS Form
plugin — questions appear as earlier ones are answered, results computed by
the site's own JS). **We drive the real page rather than reimplementing its
logic**, so the recommendation is guaranteed identical to what a human would
get. Each question is answered from the code chunks most relevant to it
(`backend/code_index.py` — LlamaIndex + a local embedding model via
**fastembed** (ONNX Runtime), no external embeddings API), not the whole
project at once. Anything answered with low confidence goes into
`needs_human_input` — with the real options the checker itself offers —
instead of being silently guessed; `POST .../{session_id}/answer` resumes
with human-provided answers (session cached server-side in
`backend/session_store.py`, in-memory, 30min TTL, doesn't survive a restart
or scale beyond one instance — documented trade-off), validated against the
real options before any browser automation runs again. The LLM's own answers
are normalized the same way (`normalize_llm_answer`): options not in the form
are dropped, several answers to a radio question go to the human, transient
Mistral errors (429/5xx, connection drops) are retried with backoff. Code and
PDF excerpts are passed to the LLM as delimited *data*, with an explicit
instruction not to follow instructions found inside them (prompt injection).
Zip extraction, hashing, Repomix, PDF parsing and indexing run in worker
threads, so a large upload doesn't stall other requests or `/health`.
Indexing is CPU-bound (fastembed's ONNX runtime, ~2.7x sentence-transformers:
28 → 76 chunks/s on a 1MB test project); since spec 007 it no longer races
a request timeout, but a true 500MB project would still take on the order of
an hour to index and hold a queue slot that long (see
`specs/002-rag-code-retrieval/research.md`).

**A two-stage variant was tried and reverted** (`specs/004-two-stage-analysis/`):
summarize the whole project once, surface information gaps to the human
*before* running the browser, then fill the form from that summary instead
of per-question retrieval. It worked and was verified live, but became
unnecessary once the LLM provider switch below made a full form-filling run
fast enough (~10s) that avoiding one wasn't worth the extra
`analyze`/`resolve-gaps`/`run` round-trips. Code was removed; the spec is
kept as a record of what was tried and why — see its `spec.md` Status.

**PDF document input (spec 006)**: `file` (code) and a new `pdf` field are both
optional on `/compliance-check`, but at least one is required. `backend/pdf_extract.py`
extracts whatever text is present in the PDF's pages via `pypdf` (pure Python, no OCR,
no system dependency); a page with no text layer (scanned/image-only) is simply
skipped, and the user is warned (`pdf_warning` in the response) if a meaningful share
of the document couldn't be read this way — the check still runs on whatever *was*
extracted rather than failing outright. The extracted text is formatted with the same
`## File: <name> (page N)` header Repomix's own output uses, then concatenated with
the Repomix representation into one string — so `code_index.py`'s chunker/retriever
needed **zero changes** to serve PDF-derived facts through the exact same per-question
flow as code. Live-verified: a question left unresolved (low confidence) by code alone
*and* by the PDF alone was answered correctly, at high confidence, once both were
supplied together — proof both sources are genuinely consulted, not one silently
preferred. See `specs/006-pdf-document-input/`.

`backend/Dockerfile` — Python + Node (for Repomix) + Playwright/Chromium +
pre-downloaded embedding model.

**LLM provider**: **Mistral's free API** (`mistral-small-latest`). Originally
Z.AI (`glm-4.5-flash`, free tier) — live benchmarking found its per-call
latency wildly inconsistent (0.3s to 80+s under real conditions) and
`glm-4.7-flash` even worse (mostly `429` "temporarily overloaded"). Switched
after live-benchmarking Mistral the same way: 8 back-to-back calls all
landed under 1s, no throttling, no cold starts. A full one-shot compliance
check now completes in ~7-10s end-to-end, down from 40-80s+ for a single
question on Z.AI. Backend-side waste that *was* fixable regardless of
provider has also been fixed (redundant HuggingFace Hub network checks on
every request, a fresh TLS connection per LLM call).

## API

### 🔒 `POST /api/v1/analyses`
Upload a file/zip (`file`), optional `output_format` (`xml`|`markdown`).
Returns the Repomix representation of the project. No compliance logic.
Unused by the UI; requires login since it accepts the same 500 MB uploads.

### Auth — `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
Register/login body `{"email", "password"}` (password ≥ 8 chars) → `{"access_token",
"token_type": "bearer", "user"}`. `409` email taken (case-insensitive), same
`401` for unknown email and wrong password. All routes marked 🔒 below need
`Authorization: Bearer <token>` (`401` otherwise).

### 🔒 `POST /api/v1/compliance-check`
Upload a file/zip (`file`) and/or a PDF (`pdf`) — **at least one is required**
(spec 006) — plus optional `company_name`, `company_context` (free text, e.g.
policy doc contents). Validates everything (formats, sizes, zip entries,
PDF), saves the analysis as `queued` and returns **`202`** immediately (spec
007):
```json
{"analysis_id": "uuid", "status": "queued", "queue_position": 3,
 "estimated_wait_seconds": 120, "filename": "app.zip + register.pdf",
 "pdf_warning": "…"}
```
`queue_position` 0 = starting now. The job then runs Repomix (if `file`),
uses the PDF text (if `pdf`), runs the compliance agent and saves the result;
follow it with `GET /api/v1/history/{analysis_id}`. Once `done`, that returns:
```json
{
  "session_id": "a1b2c3...",
  "analysis_id": "uuid",
  "status": "done",
  "is_complete": true,
  "results_text": "<the checker's own recommendation, as plain text>",
  "questions_answered": 6,
  "question_details": [
    {"field_id": "...", "type": "radio", "question": "...", "answer": ["Provider"],
     "reasoning": "...", "confidence": "high", "source": "ai"}
  ],
  "needs_human_input": [
    {"field_id": "wsf-1-field-57-row-1", "type": "radio", "question": "...",
     "reasoning": "...", "options": ["Provider", "Deployer", "..."]}
  ],
  "pdf_warning": "1 page(s) sur 3 du PDF n’ont pas pu être lues comme texte..."
}
```
`400` if neither `file` nor `pdf` is provided, or if `pdf` isn't a valid PDF.
`pdf_warning` is present only when a meaningful share of a submitted PDF's
pages had no extractable text (scanned/image-only — not OCR'd, spec 006); it
is saved with the analysis and returned again on resume and in history.
`429` if the user already has `MAX_ACTIVE_CHECKS_PER_USER` analyses queued or
running; `503` only if the bounded queue is full. A failed job ends as
`status: failed` with a French `error` (e.g. Repomix failure, provider down
after retries, server restart). `409` on register is also returned for two
simultaneous sign-ups with the same email (no `500`); login costs the same
argon2 time for an unknown email.

### 🔒 `POST /api/v1/compliance-check/{session_id}/answer`
Resume a check with human-provided answers, without re-uploading the file
(reuses the code index cached from the first call). Body:
```json
{"answers": [{"field_id": "wsf-1-field-57-row-1", "value": "Provider"}]}
```
`value` is a string for `radio`/text-like fields, a string array for
`checkbox`. Queued like a submission: returns `202` with the same shape
(+ `session_id`), the analysis goes back to `queued` and is updated in place
when the run ends. `400` if a multiple-choice value isn't one of that
question's real options (before anything is queued; a batch with one invalid
value is rejected whole); `404` if `session_id` is unknown, its 30-minute TTL
expired (the TTL is paused while a resume waits/runs), or it belongs to
another user; `409` if a resume for that analysis is already queued/running;
`429`/`503` as above. Questions the AI already answered earlier in this
analysis are reused, not re-asked. Free-text answers are applied too (they
used to be silently dropped — fixed in spec 005).

### 🔒 `GET /api/v1/history`, `GET /api/v1/history/{analysis_id}`
Current user's analyses, newest first (each with `status`); detail returns the
saved result (fields above incl. `pdf_warning`, + `status`, `error`,
`queue_position`/`estimated_wait_seconds` while queued, `started_at`/`finished_at`,
`created_at`/`updated_at`/`content_fingerprint`), with `session_id` only while
its in-memory session can still be resumed and no run is queued/running.
`404` if not owned by the caller.

### `GET /health`
Liveness check.

### CORS
Allowed origins hardcoded in `main.py`: `localhost:3000`,
`https://cowsay-one.vercel.app`. Add new frontend URLs there.

## Required env vars (backend)

- `MISTRAL_API_KEY` — required for every LLM call (one per form question
  the AI answers), Mistral's La Plateforme API (`api.mistral.ai/v1/chat/completions`,
  OpenAI-compatible). Free tier — live-benchmarked as fast and stable (see
  above); get a key at [console.mistral.ai](https://console.mistral.ai).
- `MISTRAL_MODEL` — optional, defaults to `mistral-small-latest`.
- `DATABASE_URL` — required, e.g. `postgresql+psycopg://cowsay:pass@localhost:5432/cowsay`
  (local PostgreSQL now, Supabase/Neon once deployed — same code).
- `JWT_SECRET` — required, long random string
  (`python -c "import secrets;print(secrets.token_urlsafe(48))"`).
- Optional queue limits (spec 007, see above): `MAX_CONCURRENT_CHECKS` (4 —
  checks running at once; ~250 MB each measured), `MAX_ACTIVE_CHECKS_PER_USER`
  (2), `MAX_QUEUED_CHECKS` (50), `MAX_QUEUED_UPLOAD_BYTES` (8 GiB, under
  Fargate's 20 GB ephemeral storage).

## Run locally

Needs a PostgreSQL database first (once):
`sudo -u postgres createuser --pwprompt cowsay && sudo -u postgres createdb -O cowsay cowsay`.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # once, for compliance-check
cp .env.example .env && edit .env with your key     # loaded automatically at startup
python run.py                                       # NOT `uvicorn main:app` on Windows — see below
```

On Windows, launch with `python run.py` (not the `uvicorn` CLI directly). Playwright
needs the Proactor event loop to spawn its browser subprocess; that has to be set
*before* uvicorn creates its loop, which `run.py` does — the `uvicorn main:app` CLI
creates its loop before `main.py` is even imported, too late to patch from inside it.
On Linux/macOS/Docker this isn't needed; `uvicorn main:app --reload --port 8000` works
fine there.

```bash
cd frontend
cp .env.exemple .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm ci && npm run dev
```

Docker: `cd backend && docker build -t cowsay-backend . && docker run --rm -p 8000:8000 --env-file .env -e DATABASE_URL=... -e JWT_SECRET=... cowsay-backend`
(from inside the container, a local database is `host.docker.internal`, not `localhost`).
The image runs as non-root user `app`; Chromium lives in `/ms-playwright`.

Tests (no database, network or model needed — LLM calls are mocked):
`cd backend && pip install -r requirements-dev.txt && python -m pytest tests`.

## Deployment

Target architecture (production-shaped, not a POC, per grading rubric):

- **Compute:** AWS ECS on Fargate (Express mode), cluster `default`, service
  `cowsay-backend-dcab`, ECS's default rolling deployment
  (`wait-for-service-stability: true`) — not a Canary.
- **Images:** Docker, built from `backend/` and pushed to Amazon ECR, tagged
  with the commit SHA.
- **Database/auth:** PostgreSQL via `DATABASE_URL`; `DATABASE_URL`,
  `JWT_SECRET` and `MISTRAL_API_KEY` are set by hand on the ECS task
  definition. Tables are created at startup; later columns are added by an
  idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `db.init_db` (no
  migration tool yet).

CI/CD: `.github/workflows/deploy.yml`. Job `test` (every push to `main` and
every pull request): backend `pytest`, frontend `eslint` + `tsc --noEmit`.
Job `deploy` (push to `main` only, `needs: test`): AWS auth (`us-east-1`,
long-lived `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` secrets — OIDC would be
safer), Docker Buildx with GitHub Actions layer cache (`type=gha`),
build+push to ECR, fetch the current ECS task definition, swap in the new
image, deploy to Fargate.

Production sizing (live-verified): the service runs in ECS Express mode, so the
ALB is `ecs-express-gateway-alb-*`.

- Task size: **2 vCPU / 8 GB** (the default wizard size caused 504s back when
  a check was one synchronous request). Fits the default 4 parallel checks
  with wide margin (< 1 GB measured under `--cpus 2 --memory 8g`).
- **Desired count = 1 task, no autoscaling out** (queue, sessions and AI-answer
  memory are in-process — a 2nd task would 404 resumes and split the queue).
  Check the service's autoscaling policy (Express mode can create one).
- ALB `idle_timeout.timeout_seconds` = **300** (default 60). Since spec 007 no
  request lasts more than a few seconds (checks are queued jobs), so this is
  no longer load-bearing; uploads of large zips still take time to transfer.
- Change CPU/memory/env vars via a new revision of `default-cowsay-backend-dcab`;
  `deploy.yml` reuses the latest revision and only swaps the image.
- A redeploy fails the analyses queued/running at that moment (users see
  "interrompue par un redémarrage — merci de la relancer").

## Git workflow for this repo

One branch per feature / major chunk, pushed as soon as it works — so any
broken change is easy to roll back from. Don't accumulate multiple features
on one local branch.

## Development process (Spec Kit)

Rubric requires a spec-driven workflow when using an AI coding harness. Rules
live in [`.specify/memory/constitution.md`](.specify/memory/constitution.md).
Non-trivial features go through: `/speckit-specify` → `/speckit-plan` →
`/speckit-tasks` → `/speckit-implement`, with artifacts under `specs/`.
`specs/001-compliance-check-agent/spec.md` documents the compliance-check
feature retroactively (built before Spec Kit was adopted); everything after
that should have specs written before implementation.

## Status / what's left

Done:
- Repomix conversion endpoint.
- Compliance-check endpoint: drives the real checker form end-to-end. Each
  question answered from the code chunks relevant to it (`code_index.py`,
  spec 002). Human-in-the-loop answers (`session_store.py`, spec 003):
  unresolved questions come back with real options, an invalid answer is
  rejected before any browser automation runs, frontend renders
  radio/checkbox/text inputs.
- Fast, stable LLM provider (Mistral, `mistral-small-latest`) — a full
  one-shot check now completes in ~7-10s, live-verified after switching from
  Z.AI (which was 40-80s+ per single question, unusably slow).
- Accounts + per-user history (spec 005): login required to analyze, every
  check saved with per-question detail, "Mes analyses" page, `/analyse?id=`
  reloads any saved result. Free-text human answers fixed.
- PDF document input (spec 006): a check can run from a PDF alone, code alone,
  or both — live-verified all three, including a fact only resolvable when
  both sources are combined. No OCR; unreadable pages are skipped with a
  warning shown to the user, not silently ignored.
- Review hardening: session purge, blocking work off the event loop,
  concurrency cap, Mistral retry, LLM answer validation, prompt-injection
  framing, login timing + sign-up race, zip file-count limit, persisted
  `pdf_warning`, non-root Docker image, first test suite + CI gate.
- 10+ simultaneous users (spec 007): queued async checks with position /
  estimate, per-user limit, LLM quota pacing, halved prompt tokens (same
  answers on the reference projects), AI answers reused on resume, shared
  browser — 24 simultaneous users live-verified, 0 provider `429`.

Not done yet (from the original brief):
- Cross-checking the checker's recommendation against the actual AI Act
  article text (the brief asks the agent to independently verify which
  article applies, not just trust the checker's own output).
- A structured "summary of the verification" report (`needs_human_input` is
  raw, not written up as a narrative). A two-stage summarize-then-fill
  approach was built and verified for this (`specs/004-two-stage-analysis/`)
  but reverted once Mistral made the underlying speed problem it solved
  moot — revisit if a written summary becomes valuable independent of speed.
- Visual polish on the frontend compliance-check flow — functional, not
  designed. `frontend/app/compliance/page.tsx` is a separate bare-bones page,
  for quick API-only testing. `/api/v1/analyses` (Repomix-only output) is no
  longer used by any page but still exists as an endpoint (login required).
- Tests cover pure logic only (`backend/tests/`: LLM answer normalization,
  retry and pacing, answer reuse, job queue, zip limits/traversal, session
  expiry, PDF extraction). No endpoint/DB tests and no browser test against
  the real checker — those are still verified live (scripts in spec 007's
  quickstart).
- `is_complete` is derived by string-matching the checker's results text
  ("incomplete"/"not yet completed") — breaks silently if the site rewords it.
- ECS env vars (`MISTRAL_API_KEY`, `DATABASE_URL`, `JWT_SECRET`) are edited by
  hand on the task definition, not managed as code.
- Rate limiting is per active analysis (2 per user), not per request/minute.
- Reusing a previous result for an identical project (the fingerprint is
  stored for this, spec 005) — not built; a check always re-runs.
- Queue, sessions and AI-answer memory are in-memory/single-process — lost on
  restart (queued/running analyses are then marked failed), and not
  shareable across ECS tasks: horizontal scaling needs shared storage for all
  three (out of scope of spec 007). Throughput ceiling on the free Mistral
  tier: ~40 questions/minute platform-wide on a real project (~2.2 k tokens
  each), up to ~90/minute for tiny ones (request limit).
- The wait estimate only knows average run duration, not provider pacing: it
  can under-estimate when the quota is saturated.
- True 500MB-project support: upload size limits (`MAX_FILE_SIZE` etc. in
  `main.py`) are already raised to 500MB, but `code_index.py`'s indexing
  would take on the order of an hour at current throughput for a project that
  large, holding a queue slot all along — needs a faster embedding setup (see
  `specs/002-rag-code-retrieval/research.md`).
- OCR for scanned/image-only PDFs — deliberately out of scope (spec 006): a
  system-level OCR dependency for a compliance tool risks confidently-wrong
  answers from misread text, worse than the current "skip and warn" behavior.
