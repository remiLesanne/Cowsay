# Quickstart: validating Concurrent Analyses

Prerequisites: backend running locally (`python run.py`) against a PostgreSQL database,
`MISTRAL_API_KEY` set, frontend on `localhost:3000`. Contracts: [contracts/api.md](contracts/api.md).

## 1. Unit tests

`cd backend && python -m pytest tests` — includes queue ordering/positions/limits, restart
recovery, the LLM pacing limiter (fake clock) and AI-answer reuse.

## 2. One analysis, asynchronous (US1)

Submit a small code file from the UI. Expected: the page switches to the analysis within a
few seconds showing "En cours", then the result appears without reloading. Close the tab
mid-run, reopen from "Mes analyses": status or result shown.

## 3. 12 users at once (US2, SC-001/002/004/005)

Load script (kept out of the repo, in the session scratchpad): registers 12 accounts and
submits 12 small code-only analyses concurrently, then polls each until done.

Expected: 12 × `202` each in < 5 s; while waiting, `queue_position` decreases and
`estimated_wait_seconds` is present; 12/12 end `done`; total time ≤ 10 min; server log
shows no LLM `429`/"retrying" lines; a 3rd concurrent submission by the same account gets
`429`.

## 4. Resume through the queue, no repeated questions (US3, SC-006)

Run an analysis that ends with pending questions; answer one while other analyses are
queued. Expected: `202` with `status: queued`, then `done`; the backend log for the resume
shows LLM calls only for newly revealed fields (count them against the first run's
`[iter …] field … (…, ai)` lines). A second answer submission while it's queued → `409`.

## 5. Token reduction without quality loss (US4, SC-007)

Run the reference projects (this repo's `backend/*.py`, the spec 006 PDF + code pair, a
code-only sample) with the old chunk settings and the new ones, `temperature: 0`.
Expected: prompt tokens per question down ≥ 30 %; identical answers and escalations.

## 6. Parallelism (US5, SC-008)

In the Docker image with `--memory 8g --cpus 2`: 4 concurrent analyses progress at the
same time (4 "running" at once in `GET /history/{id}`), all complete, `docker stats`
stays well under 8 GB, `/health` keeps answering.

## 7. Restart recovery (FR-015)

Submit 3 analyses, stop the server while they're queued/running, start it again.
Expected: all 3 shown as failed with the "redémarrage" message; no leftover temp uploads.
