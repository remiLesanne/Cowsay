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
             /api/v1/compliance-check                (Repomix + Playwright agent -> checker verdict, one call)
             /api/v1/compliance-check/{id}/answer    (resume with human answers for unresolved questions)
```

`POST /api/v1/compliance-check` is the one-shot flow (specs 002/003): upload
→ Repomix → `backend/compliance_agent.py` drives a headless Chromium through
the official checker's form (a dynamic branching questionnaire — WS Form
plugin — questions appear as earlier ones are answered, results computed by
the site's own JS). **We drive the real page rather than reimplementing its
logic**, so the recommendation is guaranteed identical to what a human would
get. Each question is answered from the code chunks most relevant to it
(`backend/code_index.py` — LlamaIndex + a local HuggingFace embedding model,
no external embeddings API), not the whole project at once. Anything
answered with low confidence goes into `needs_human_input` — with the real
options the checker itself offers — instead of being silently guessed;
`POST .../{session_id}/answer` resumes with human-provided answers (session
cached server-side in `backend/session_store.py`, in-memory, 30min TTL,
doesn't survive a restart or scale beyond one instance — documented
trade-off), validated against the real options before any browser automation
runs again. **Known limit**: `code_index.py`'s indexing throughput is
~91 KB/s — fine up to tens of MB, but a true 500MB project would take on the
order of 90 minutes to index synchronously (not solved — see
`specs/002-rag-code-retrieval/research.md`).

**A two-stage variant was tried and reverted** (`specs/004-two-stage-analysis/`):
summarize the whole project once, surface information gaps to the human
*before* running the browser, then fill the form from that summary instead
of per-question retrieval. It worked and was verified live, but became
unnecessary once the LLM provider switch below made a full form-filling run
fast enough (~10s) that avoiding one wasn't worth the extra
`analyze`/`resolve-gaps`/`run` round-trips. Code was removed; the spec is
kept as a record of what was tried and why — see its `spec.md` Status.

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
(reuses the code index cached from the first call). Body:
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
- Compliance-check endpoint: drives the real checker form end-to-end. Each
  question answered from the code chunks relevant to it (`code_index.py`,
  spec 002). Human-in-the-loop answers (`session_store.py`, spec 003):
  unresolved questions come back with real options, an invalid answer is
  rejected before any browser automation runs, frontend renders
  radio/checkbox/text inputs.
- Fast, stable LLM provider (Mistral, `mistral-small-latest`) — a full
  one-shot check now completes in ~7-10s, live-verified after switching from
  Z.AI (which was 40-80s+ per single question, unusably slow).

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
  longer used by any page but still exists as an endpoint.
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
  `main.py`) are already raised to 500MB, but `code_index.py`'s indexing
  would take ~90 minutes synchronously at current throughput for a project
  that large — needs background processing or a faster embedding setup (see
  `specs/002-rag-code-retrieval/research.md`).
