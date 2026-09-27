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
             /api/v1/compliance-check                (Repomix + Playwright agent -> checker verdict, one call)
             /api/v1/compliance-check/{id}/answer    (resume with human answers for unresolved questions)
             /api/v1/auth/*, /api/v1/history         (accounts + saved analyses, PostgreSQL — spec 005)
             /api/v1/history/{id}/articles           (guided RAG: explains the AI Act articles the verdict cites — spec 007)
```

**AI Act article explanations (spec 007, guided RAG)**: for a complete
analysis, the result page explains each article/annex the checker's verdict
cites ("see Article 5"). *Guided*, not classic RAG: the checker decides which
articles apply (regex over its verdict, `backend/ai_act.py`); similarity
search (same fastembed model as `code_index.py`) only picks, **inside each
cited article**, the official passages closest to the analysis's answers
(e.g. 5(1)(f) emotion recognition among Article 5's 8 prohibitions); one
Mistral call (JSON mode) explains them in French from those passages only,
saying so when they don't settle which point applies. A whole-regulation
search could surface an article that merely sounds related — a confidently
wrong legal statement. Corpus: `backend/data/ai_act_en.json` (official
EUR-Lex text of Regulation (EU) 2024/1689, English passages for retrieval —
the checker and embedding model are English — plus official French titles;
reusable with attribution per Decision 2011/833/EU), built once by
`backend/scripts/build_ai_act_corpus.py` (stdlib only), so nothing external
is called at request time. Cached per analysis in `article_explanations`
keyed by a hash of the verdict (a changed verdict regenerates; a new table,
not a column, because `create_all` can't alter the existing `analyses`).

**Accounts & history (spec 005)**: running/resuming a check requires a
logged-in user (email + password, argon2, 24h JWT bearer — `backend/auth.py`).
Every successful check is saved as one `analyses` row in PostgreSQL
(`backend/db.py`, tables created at startup — no migrations yet), updated in
place on each resume round: file name, content fingerprint (SHA-256 of the
extracted files — **the code itself is never stored**), company, verdict,
per-question detail (question/answer/reasoning/source AI or human), pending
questions. Users only ever see/resume their own (others' → `404`).
Trade-offs: logout is client-side (token discarded, still valid until
expiry), token in `localStorage` (cross-origin front/back rules out cookies
without HTTPS on the backend). See `specs/005-user-accounts-history/research.md`.

`POST /api/v1/compliance-check` is the one-shot flow (specs 002/003): upload
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
real options before any browser automation runs again. **Known limit**:
indexing is still CPU-bound and synchronous within the request (root cause
of a real production 504 — see Deployment below), though switched from
sentence-transformers/PyTorch to fastembed's ONNX runtime for the same model,
live-benchmarked at ~2.7x the throughput (28 → 76 chunks/s on a 1MB test
project, same machine). Fine up to tens of MB; a true 500MB project would
still take on the order of half an hour to index synchronously (not solved —
see `specs/002-rag-code-retrieval/research.md`).

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

### `POST /api/v1/analyses`
Upload a file/zip (`file`), optional `output_format` (`xml`|`markdown`).
Returns the Repomix representation of the project. No compliance logic.

### Auth — `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
Register/login body `{"email", "password"}` (password ≥ 8 chars) → `{"access_token",
"token_type": "bearer", "user"}`. `409` email taken (case-insensitive), same
`401` for unknown email and wrong password. All routes marked 🔒 below need
`Authorization: Bearer <token>` (`401` otherwise).

### 🔒 `POST /api/v1/compliance-check`
Upload a file/zip (`file`) and/or a PDF (`pdf`) — **at least one is required**
(spec 006) — plus optional `company_name`, `company_context` (free text, e.g.
policy doc contents). Runs Repomix (if `file`), extracts PDF text (if `pdf`),
combines both into one context, runs the compliance agent, then saves the
analysis. Returns:
```json
{
  "session_id": "a1b2c3...",
  "analysis_id": "uuid",
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
pages had no extractable text (scanned/image-only — not OCR'd, spec 006).

### 🔒 `POST /api/v1/compliance-check/{session_id}/answer`
Resume a check with human-provided answers, without re-uploading the file
(reuses the code index cached from the first call). Body:
```json
{"answers": [{"field_id": "wsf-1-field-57-row-1", "value": "Provider"}]}
```
`value` is a string for `radio`/text-like fields, a string array for
`checkbox`. Returns the same shape as the original endpoint. `400` if a
multiple-choice value isn't one of that question's real options (before any
browser automation runs; a batch with one invalid value is rejected whole);
`404` if `session_id` is unknown, its 30-minute TTL expired, or it belongs to
another user. Free-text answers are applied too (they used to be silently
dropped — fixed in spec 005). Updates the same saved analysis.

### 🔒 `GET /api/v1/history`, `GET /api/v1/history/{analysis_id}`
Current user's analyses, newest first; detail returns the saved result
(same fields as above + `created_at`/`updated_at`/`content_fingerprint`),
with `session_id` only while its in-memory session can still be resumed.
`404` if not owned by the caller.

### 🔒 `GET /api/v1/history/{analysis_id}/articles`
Explanations of the articles/annexes the saved verdict cites (spec 007):
`{"status": "ready"|"incomplete"|"no_references", "articles": [{"ref", "title",
"url", "passages": [{"label", "text"}], "explanation", "why_it_applies",
"what_it_implies", "available"}], "see_also": [{"ref", "title", "articles",
"url"}]}`. Generated on first call (~3-5s), then served from the database
until the verdict changes; `incomplete` without any AI call for a non-final
verdict; `404` if not owned; `502`/`504` if Mistral fails (nothing cached).

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
- `DATABASE_URL` — required, e.g. `postgresql+psycopg://cowsay:pass@localhost:5432/cowsay`
  (local PostgreSQL now, Supabase/Neon once deployed — same code).
- `JWT_SECRET` — required, long random string
  (`python -c "import secrets;print(secrets.token_urlsafe(48))"`).

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

Docker: `cd backend && docker build -t cowsay-backend . && docker run --rm -p 8000:8000 cowsay-backend`
(pass `-e MISTRAL_API_KEY=...`).

## Deployment

Target architecture (production-shaped, not a POC, per grading rubric):

- **Compute:** AWS ECS on Fargate, cluster `default`, service
  `cowsay-backend-dcab`, deployed as a Canary (~3 min bake time,
  `wait-for-service-stability: true`).
- **Images:** Docker, built from `backend/` and pushed to Amazon ECR, tagged
  with the commit SHA.
- **Database/auth:** built (spec 005) against local PostgreSQL; production
  target is external managed PostgreSQL (Supabase or Neon) via `DATABASE_URL`
  — not provisioned yet, and `DATABASE_URL`/`JWT_SECRET` must be added to the
  ECS task definition before a deploy.

CI/CD: `.github/workflows/deploy.yml` runs on every push to `main` —
checkout, AWS auth (`us-east-1`), Docker Buildx with GitHub Actions layer
cache (`type=gha`), build+push to ECR, fetch the current ECS task definition,
swap in the new image, deploy to Fargate. Needs `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` GitHub secrets, and `MISTRAL_API_KEY` set on the
ECS task definition for compliance-check to work in production.

Production sizing (live-verified): the service runs in ECS Express mode, so the
ALB is `ecs-express-gateway-alb-*`. `/compliance-check` is one synchronous
request and building the embedding index is CPU-bound (~108s for a 1 MB upload
on a small task), so:

- Task size: **2 vCPU / 8 GB** (the default wizard size caused 504s).
- ALB `idle_timeout.timeout_seconds` = **300** (default 60 → 504 with no CORS
  headers). Set via `aws elbv2 modify-load-balancer-attributes`; Express mode
  may reset it on redeploy — re-check if 504s reappear.
- Change CPU/memory/env vars via a new revision of `default-cowsay-backend-dcab`;
  `deploy.yml` reuses the latest revision and only swaps the image.
- Durable fix if this bites again: make the endpoint an async job (job id +
  polling) so no request depends on the ALB timeout.

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
- AI Act article explanations (spec 007, guided RAG): each article/annex the
  verdict cites, with the official passages matching the answers and a French
  explanation (why it applies, what it implies), cached per verdict.
  Live-verified: an emotion-recognition project's "Prohibited — Article 5"
  verdict is explained from 5(1)(f).
- PDF document input (spec 006): a check can run from a PDF alone, code alone,
  or both — live-verified all three, including a fact only resolvable when
  both sources are combined. No OCR; unreadable pages are skipped with a
  warning shown to the user, not silently ignored.

Not done yet (from the original brief):
- Independently re-deriving *which* articles apply (the brief's "verify,
  don't just trust the checker"): spec 007 deliberately trusts the checker's
  citations and explains them against the official text — it doesn't audit
  the checker's legal reasoning. Recitals aren't in the corpus; incomplete
  verdicts get no explanation.
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
- `MISTRAL_API_KEY` is set directly on the ECS task definition (not in CI
  secrets; edited by hand, not managed as code). `DATABASE_URL` and
  `JWT_SECRET` (spec 005) are not wired in yet, and no managed PostgreSQL is
  provisioned — accounts/history won't work in production until both are set.
- Reusing a previous result for an identical project (the fingerprint is
  stored for this, spec 005) — not built; a check always re-runs.
- Session cache (`session_store.py`) is in-memory/single-process — lost on
  restart, doesn't scale beyond one instance (documented trade-off, not an
  oversight).
- True 500MB-project support: upload size limits (`MAX_FILE_SIZE` etc. in
  `main.py`) are already raised to 500MB, but `code_index.py`'s indexing
  would take ~90 minutes synchronously at current throughput for a project
  that large — needs background processing or a faster embedding setup (see
  `specs/002-rag-code-retrieval/research.md`).
- OCR for scanned/image-only PDFs — deliberately out of scope (spec 006): a
  system-level OCR dependency for a compliance tool risks confidently-wrong
  answers from misread text, worse than the current "skip and warn" behavior.
