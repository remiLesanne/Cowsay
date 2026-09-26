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
  - Loop: scan visible questions -> ask an LLM (Z.AI, GLM models) to answer each
    from the Repomix code text + optional company context -> click/fill ->
    repeat until no new questions appear -> scrape the "Your results" section
    of the page as plain text.
  - Any answer given with low confidence (or left unanswered) is collected
    into `needs_human_input` in the response instead of being silently
    guessed away.
- `backend/Dockerfile` — Python + Node (for Repomix) + Playwright/Chromium.
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
  "is_complete": true,
  "results_text": "<the checker's own recommendation, as plain text>",
  "questions_answered": 6,
  "needs_human_input": [{"question": "...", "reasoning": "..."}]
}
```

### `GET /health`
Liveness check.

### CORS
Allowed origins hardcoded in `main.py`: `localhost:3000`,
`https://cowsay-one.vercel.app`. Add new frontend URLs there.

## Required env vars (backend)

- `ZAI_API_KEY` — required for `/api/v1/compliance-check` (LLM calls go to
  Z.AI's API, `api.z.ai/api/paas/v4/chat/completions`, OpenAI-compatible).
- `ZAI_MODEL` — optional, defaults to `glm-4.6`.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # once, for compliance-check
cp .env.example .env && edit .env with your key     # loaded automatically at startup
uvicorn main:app --reload --port 8000
```

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

Not done yet (from the original brief):
- Cross-checking the checker's recommendation against the actual AI Act
  article text (the brief asks the agent to independently verify which
  article applies, not just trust the checker's own output).
- A structured "summary of the verification" + explicit missing-info report
  (`needs_human_input` exists but is raw, not written up).
- Frontend UI for the compliance-check flow (upload + company info form,
  results display) — frontend currently only calls `GET /`.
- No automated tests yet for either backend endpoint.
- `ZAI_API_KEY` is not wired into the ECS task definition / CI secrets.
- No database or auth: no user model, DB client, or `DATABASE_URL` usage
  anywhere in `backend/` yet, despite being part of the target architecture.
