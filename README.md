# Cowsay — EU AI Act Compliance Checker

**Goal (school project, EPF 5A):** given a codebase (+ optional company info),
automatically determine whether that project complies with the EU AI Act.
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
             /api/v1/compliance-check/analyze        (Repomix + one LLM call -> summary + gaps)
             /api/v1/compliance-check/{id}/resolve-gaps (regenerate the summary with more info)
             /api/v1/compliance-check/{id}/run       (Playwright agent, using the summary -> checker verdict)
             /api/v1/compliance-check/{id}/answer    (reactive fallback for anything `run` still flagged)
             /api/v1/compliance-check                (older single-call flow, kept working, see below)
```

Current default flow (`specs/004-two-stage-analysis/`): **understand, then fill**.
1. `analyze` — Repomix converts the upload, then one LLM call
   (`backend/project_summary.py`) produces a coherent summary of the system
   and an explicit list of information gaps — before any browser automation
   runs, so gaps surface upfront instead of only being discoverable by
   running the whole (slow) form-filling loop once already.
2. `resolve-gaps` (optional, repeatable) — the user answers a gap directly or
   uploads an extra document; the summary is regenerated from scratch each
   time (code + all extra material so far), so it stays one coherent
   document rather than a patchwork.
3. `run` — `backend/compliance_agent.py` drives a headless Chromium through
   the official checker's form (a dynamic branching questionnaire — WS Form
   plugin — questions appear as earlier ones are answered, results computed
   by the site's own JS). **We drive the real page rather than
   reimplementing its logic**, so the recommendation is guaranteed identical
   to what a human would get. Each question is answered using the current
   summary as context (not per-question code retrieval — see
   `specs/004-two-stage-analysis/research.md` for why). Anything still
   answered with low confidence goes into `needs_human_input`, never
   silently guessed.
4. `answer` (spec 003, unchanged) — resumes `run` with human answers for
   anything `needs_human_input` flagged, validated against the question's
   real options before any browser automation runs again.

`POST /api/v1/compliance-check` (specs 002/003's original single-call
endpoint: upload → full result in one call) **still exists and still works
exactly as before** — kept for backward compatibility, not deleted. It uses
`backend/code_index.py` (LlamaIndex + a local HuggingFace embedding model, no
external embeddings API) for per-question retrieval instead of a summary.
That module stays fully functional; the new default flow above just doesn't
call it. **Known limit** (inherited, not fixed by spec 004): its indexing
throughput is ~91 KB/s — fine up to tens of MB, but a true 500MB project
would take on the order of 90 minutes to index synchronously.

`backend/Dockerfile` — Python + Node (for Repomix) + Playwright/Chromium +
pre-downloaded embedding model. `backend/session_store.py` — in-memory,
single-process session cache (30min TTL) shared by specs 002-004; doesn't
survive a restart or scale beyond one instance (documented trade-off, not an
oversight).

**LLM provider history**: originally Z.AI (`glm-4.5-flash`, free tier). Live
benchmarking found its per-call latency wildly inconsistent (0.3s to 80+s
under real conditions) and `glm-4.7-flash` even worse (mostly `429`
"temporarily overloaded"). Switched to **Mistral's free API**
(`mistral-small-latest`) after live-benchmarking it the same way: 8
back-to-back calls all landed under 1s, no throttling, no cold starts — see
git history on `feature/two-stage-analysis` for the raw numbers. Backend-side
waste that *was* fixable regardless of provider has also been fixed
(redundant HuggingFace Hub network checks on every request, a fresh TLS
connection per LLM call — see `feature/human-in-the-loop-answers` history).
Spec 004 doesn't reduce the number of per-question LLM calls during
form-filling; it reduces wasted full form-filling runs by surfacing gaps
before running the browser.

## API

### `POST /api/v1/analyses`
Upload a file/zip (`file`), optional `output_format` (`xml`|`markdown`).
Returns the Repomix representation of the project. No compliance logic.

### `POST /api/v1/compliance-check/analyze`
Upload a file/zip (`file`), optional `company_name`, `company_context`.
Returns `{session_id, filename, file_count, summary, gaps}` where `gaps` is
`[{id, description}]`.

### `POST /api/v1/compliance-check/{session_id}/resolve-gaps`
Form fields: `answers` (JSON string, `[{"gap_id": "...", "text": "..."}]`)
and/or `file` (an extra document, read as plain text). Regenerates and
returns `{session_id, summary, gaps}`.

### `POST /api/v1/compliance-check/{session_id}/run`
No body. Runs the actual form-filling using the session's current summary.
Returns:
```json
{
  "session_id": "a1b2c3...",
  "is_complete": true,
  "results_text": "<the checker's own recommendation, as plain text>",
  "questions_answered": 6,
  "needs_human_input": [
    {"field_id": "wsf-1-field-57-row-1", "type": "radio", "question": "...",
     "reasoning": "...", "options": ["Provider", "Deployer", "..."]}
  ]
}
```

### `POST /api/v1/compliance-check/{session_id}/answer`
Resume a `run` with human-provided answers, without re-uploading the file.
Body:
```json
{"answers": [{"field_id": "wsf-1-field-57-row-1", "value": "Provider"}]}
```
`value` is a string for `radio`/text-like fields, a string array for
`checkbox`. Returns the same shape as `run`. `400` if a multiple-choice value
isn't one of that question's real options (before any browser automation
runs); `404` if `session_id` is unknown or its 30-minute TTL expired.

### `POST /api/v1/compliance-check` (legacy, still functional)
The original single-call flow from specs 002/003: upload + optional
`company_name`/`company_context` → full result in one call, using
per-question code retrieval instead of a summary. Same response shape as
`run` above (plus `filename`/`file_count`). Used by
`frontend/app/compliance/page.tsx` (the bare-bones test page); not used by
the main upload flow anymore.

### `GET /health`
Liveness check.

### CORS
Allowed origins hardcoded in `main.py`: `localhost:3000`,
`https://cowsay-one.vercel.app`. Add new frontend URLs there.

## Required env vars (backend)

- `MISTRAL_API_KEY` — required for every LLM call (project summary + form
  answers), Mistral's La Plateforme API (`api.mistral.ai/v1/chat/completions`,
  OpenAI-compatible). Free tier — live-benchmarked as fast and stable (see
  above); get a key at [console.mistral.ai](https://console.mistral.ai).
- `MISTRAL_MODEL` — optional, defaults to `mistral-small-latest`.

## Run locally

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

Docker: `cd backend && docker build -t cowsay-backend . && docker run --rm -p 8000:8000 cowsay-backend`
(pass `-e MISTRAL_API_KEY=...`).

## Deployment

Target architecture (production-shaped, not a POC, per grading rubric):

- **Compute:** AWS ECS on Fargate, cluster `default`, service
  `cowsay-backend-dcab`, deployed as a Canary (~3 min bake time,
  `wait-for-service-stability: true`).
- **Images:** Docker, built from `backend/` and pushed to Amazon ECR, tagged
  with the commit SHA.
- **Database/auth (planned, not yet built):** external managed PostgreSQL
  (Supabase or Neon) for users, reached via a `DATABASE_URL`-style env var.
  No DB/auth code exists in `backend/` yet — see Status below.

CI/CD: `.github/workflows/deploy.yml` runs on every push to `main` —
checkout, AWS auth (`us-east-1`), Docker Buildx with GitHub Actions layer
cache (`type=gha`), build+push to ECR, fetch the current ECS task definition,
swap in the new image, deploy to Fargate. Needs `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` GitHub secrets, and `MISTRAL_API_KEY` set on the
ECS task definition for compliance-check to work in production.

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
- Two-stage compliance-check flow (`analyze` → `resolve-gaps` → `run` →
  `answer`, see `specs/004-two-stage-analysis/`): one LLM call produces a
  coherent project summary + explicit information gaps before any browser
  automation runs; gaps are resolvable by direct answer or extra document
  upload; form-filling uses the summary as context. **Validated live
  end-to-end** (2026-09-26): a plain Flask app got a summary + 8 gaps,
  resolving 2 by text correctly updated the regenerated summary, and the
  form-filling run correctly flagged one genuinely ambiguous question for a
  human instead of guessing.
- The older single-call flow (`POST /api/v1/compliance-check`, specs
  002/003) still exists and works, using retrieval (`code_index.py`,
  LlamaIndex + local embeddings) instead of a summary — kept for backward
  compatibility. Human-in-the-loop answers (`session_store.py`,
  `specs/003-human-in-loop-answers/`) work against either flow: unresolved
  questions come back with real options, an invalid answer is rejected
  before any browser automation runs, frontend renders radio/checkbox/text
  inputs.

Not done yet (from the original brief):
- Cross-checking the checker's recommendation against the actual AI Act
  article text (the brief asks the agent to independently verify which
  article applies, not just trust the checker's own output).
- Visual polish on the frontend compliance-check flow — functional, not
  designed. `frontend/app/compliance/page.tsx` is a separate bare-bones page
  hitting the legacy single-call endpoint, for quick API-only testing.
  `/api/v1/analyses` (Repomix-only output) is no longer used by any page but
  still exists as an endpoint.
- No automated tests yet for any backend endpoint — every verification in
  this project so far has been live manual/scripted testing against the real
  API, not a committed test suite.
- `MISTRAL_API_KEY` is not wired into the ECS task definition / CI secrets.
- Session cache (`session_store.py`) is in-memory/single-process — lost on
  restart, doesn't scale beyond one instance (documented trade-off, not an
  oversight).
- No database or auth: no user model, DB client, or `DATABASE_URL` usage
  anywhere in `backend/` yet, despite being part of the target architecture.
- True 500MB-project support: upload size limits (`MAX_FILE_SIZE` etc. in
  `main.py`) haven't been raised for the new flow, and even once raised, the
  legacy retrieval path's indexing would take ~90 minutes synchronously at
  current throughput for a project that large — needs background processing
  or a faster embedding setup (see `specs/002-rag-code-retrieval/research.md`).
- LLM per-call latency (0.3-80+s observed live on the free `glm-4.5-flash`
  tier) is not something spec 004 fixes — it reduces wasted *whole
  form-filling runs*, not the cost of each individual LLM call.
- One-shot summarization only (no map-reduce for very large projects) — same
  category of scale gap as the 500MB retrieval limit, deferred the same way
  (see `specs/004-two-stage-analysis/research.md`).
