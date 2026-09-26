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
                              /api/v1/analyses         (Repomix: code -> AI-readable text)
                              /api/v1/compliance-check (Repomix + Playwright agent -> checker verdict)
```

- `backend/main.py` — FastAPI app, CORS, both endpoints.
- `backend/compliance_agent.py` — the compliance agent: drives a headless
  Chromium (Playwright) through the official checker's form. The form is a
  dynamic branching questionnaire (WS Form plugin) — questions appear as
  earlier ones are answered, and results are computed client-side by the
  site's own JS. **We drive the real page rather than reimplementing its
  logic**, so the returned recommendation is guaranteed identical to what a
  human would get — no risk of drift from a reimplementation.
  - Loop: scan visible questions -> retrieve the relevant code for that
    question (`code_index.py`) -> ask an LLM (Z.AI, GLM models) to answer from
    that excerpt + optional company context -> click/fill -> repeat until no
    new questions appear -> scrape the "Your results" section as plain text.
  - Any answer given with low confidence (or left unanswered) is collected
    into `needs_human_input` in the response instead of being silently
    guessed away.
- `backend/code_index.py` — turns a Repomix representation into a queryable,
  in-memory retrieval index (LlamaIndex + a local HuggingFace embedding model,
  no external embeddings API — see `specs/002-rag-code-retrieval/research.md`)
  so each checker question is answered from the code actually relevant to it,
  regardless of project size, instead of a fixed-size prefix of the whole
  project. **Known limit**: indexing throughput is ~91 KB/s on the current
  small CPU model — fine up to tens of MB, but a true 500MB project would take
  on the order of 90 minutes to index in this synchronous request flow (not
  yet solved — see that same research.md for options).
- `backend/Dockerfile` — Python + Node (for Repomix) + Playwright/Chromium +
  pre-downloaded embedding model.
- Repomix (`backend/node_modules/.bin/repomix`) converts an uploaded file/zip
  into one AI-friendly text blob; used as the "facts about the code" input to
  both endpoints.

## API

### `POST /api/v1/analyses`
Upload a file/zip (`file`), optional `output_format` (`xml`|`markdown`).
Returns the Repomix representation of the project. No compliance logic.

### `POST /api/v1/compliance-check`
Upload a file/zip (`file`), optional `company_name`, `company_context` (free
text, e.g. policy doc contents). Runs Repomix, then the compliance agent.
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
Resume a check with human-provided answers, without re-uploading the file
(reuses the code index cached from the first call — see
`specs/003-human-in-loop-answers/`). Body:
```json
{"answers": [{"field_id": "wsf-1-field-57-row-1", "value": "Provider"}]}
```
`value` is a string for `radio`/text-like fields, a string array for
`checkbox`. Returns the same shape as the original endpoint. `400` if a
multiple-choice value isn't one of that question's real options (before any
browser automation runs); `404` if `session_id` is unknown or its 30-minute
TTL expired.

### `GET /health`
Liveness check.

### CORS
Allowed origins hardcoded in `main.py`: `localhost:3000`,
`https://cowsay-one.vercel.app`. Add new frontend URLs there.

## Required env vars (backend)

- `ZAI_API_KEY` — required for `/api/v1/compliance-check` (LLM calls go to
  Z.AI's API, `api.z.ai/api/paas/v4/chat/completions`, OpenAI-compatible).
- `ZAI_MODEL` — optional, defaults to `glm-4.5-flash` (free on Z.AI; `glm-4.6`
  and other non-Flash models require paid credit — confirmed via a 401/1113
  "Insufficient balance" error during testing).

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
(pass `-e ZAI_API_KEY=...`).

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
`AWS_SECRET_ACCESS_KEY` GitHub secrets, and `ZAI_API_KEY` set on the
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
- Compliance-check endpoint: drives the real checker form end-to-end,
  verified manually against the live site (branching logic + result
  scraping both confirmed working).
- Retrieval-based code context (`code_index.py`, see
  `specs/002-rag-code-retrieval/`): each checker question is answered from
  the code actually relevant to it (found via local embeddings), not a
  fixed-size prefix of the project. **Validated live end-to-end** against
  the real site + a real LLM call (2026-09-26) — see
  `specs/003-human-in-loop-answers/tasks.md` Phase 3 checkpoint for what that
  run found and fixed (a retrieval crash now degrades gracefully instead of
  500ing, a Windows encoding bug in the Repomix subprocess call, and a bogus
  "email" field that was being scanned as a compliance question).
- Human-in-the-loop answers (`session_store.py`, see
  `specs/003-human-in-loop-answers/`): unresolved questions come back with
  their real options; a caller can answer and resume without re-uploading the
  file (the code index is cached server-side, in-memory, 30min TTL); an
  invalid multiple-choice answer is rejected before any browser automation
  runs. Frontend renders options as radio/checkbox/text inputs.

Not done yet (from the original brief):
- Cross-checking the checker's recommendation against the actual AI Act
  article text (the brief asks the agent to independently verify which
  article applies, not just trust the checker's own output).
- A structured "summary of the verification" report (raw `needs_human_input`
  now includes options; a human-readable write-up is still not built).
- Visual polish on the frontend compliance-check flow — functional, not
  designed. `frontend/app/compliance/page.tsx` is a separate bare-bones page
  for quick API-only testing. `/api/v1/analyses` (Repomix-only output) is no
  longer used by any page but still exists as an endpoint.
- A cosmetic DOM-scraping gap: at least one checkbox question's `question`
  text comes back empty (its `field_id`/`options` are still correct and
  answerable) — see `specs/003-human-in-loop-answers/tasks.md`.
- No automated tests yet for any backend endpoint.
- `ZAI_API_KEY` is not wired into the ECS task definition / CI secrets.
- Session cache (`session_store.py`) is in-memory/single-process — lost on
  restart, doesn't scale beyond one instance (documented trade-off, not an
  oversight — see `specs/003-human-in-loop-answers/research.md`).
- No database or auth: no user model, DB client, or `DATABASE_URL` usage
  anywhere in `backend/` yet, despite being part of the target architecture.
- True 500MB-project support: upload size limits (`MAX_FILE_SIZE` etc. in
  `main.py`) haven't been raised yet, and even once raised, indexing a
  project that large would take ~90 minutes synchronously at current
  throughput — needs background processing or a faster embedding setup
  first (see `specs/002-rag-code-retrieval/research.md`).
