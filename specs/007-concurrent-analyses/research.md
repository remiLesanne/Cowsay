# Research: Concurrent Analyses

Measurements taken 2026-09-27 on the live Mistral key and this repo's backend.

## R1 — Where the capacity limit actually is

- **Decision**: treat the LLM provider quota as the platform-wide throughput ceiling and
  design around *queuing + pacing*, not raw parallelism.
- **Measured**: Mistral free tier headers: `x-ratelimit-limit-req-minute: 100`,
  `x-ratelimit-limit-tokens-minute: 100000`. One question on a real project (this repo's
  backend, 62 KB) = 4,802 prompt tokens (TOP_K_CHUNKS=5 × MAX_CHUNK_CHARS=4000). A complete
  check asks 5–10 questions → 25–50 k tokens → **2–4 complete checks per minute for the
  whole platform**, independent of server size. A burst of 10 simultaneous calls all
  returned 200 in < 0.5 s: requests/minute is not the binding limit, tokens/minute is.
- **Consequence**: 12 users at once cannot all finish in ~10 s on the free tier; they can
  all be *accepted* and served in order within a few minutes (spec SC-004: ≤ 10 min).
- **Alternatives rejected**: bigger ECS task only (doesn't raise the token ceiling);
  paid tier (user chose to stay free — pacing below reads limits from headers so a paid
  key would be used fully without code changes).

## R2 — Asynchronous jobs instead of one long request

- **Decision**: `POST /compliance-check` and `POST .../answer` validate, persist an
  `Analysis` row with status `queued`, enqueue a job, and return **202** immediately. An
  in-process FIFO queue (`backend/job_queue.py`) with `MAX_CONCURRENT_CHECKS` worker tasks
  (default 4) runs jobs; the frontend polls `GET /history/{id}` every 3 s.
- **Rationale**: removes the ALB 300 s idle timeout from the equation (SC-009) and turns
  "busy" into "waiting" (SC-001). Polling every 3 s × 12 users = 4 req/s of cheap DB reads.
- **Alternatives rejected**:
  - *Celery/RQ + Redis/SQS*: needs a broker service and a separate worker deployment, and
    the resumable session (in-memory `ProjectIndex`) would still have to live in one
    process — cost and moving parts not justified at a single-instance scale (spec
    Assumptions).
  - *WebSocket/SSE push*: nicer latency, but ALB idle timeouts and reconnect logic for a
    status that changes a handful of times per analysis; polling meets SC-003.
  - *Keep synchronous + raise ALB timeout*: still one worker per request, still 503 when
    full, and Express mode may reset the ALB attribute on redeploy (README).

## R3 — What is validated before queuing, what runs in the job

- **Decision**: at submission (synchronous, fast): extension/size checks, zip opens and
  its entry list is scanned for traversal / file-count / uncompressed-size limits
  *without extracting*, PDF text extraction (≤ 10 MB, fast) + warning, answer-option
  validation for resumes, per-user / queue-size limits. The raw upload is written to a
  private temp file. In the job: extraction, fingerprint, Repomix, indexing, browser run,
  save — then the temp file is deleted (also on failure).
- **Rationale**: FR-002 (never queue a doomed request) while keeping SC-002 (ack < 5 s):
  scanning a zip's central directory is milliseconds even for large archives; extraction
  and Repomix are not.
- **Held uploads**: kept on disk, not in memory (a 500 MB zip × a queue of 50 would not
  fit in 8 GB). Bounded by `MAX_QUEUED_UPLOAD_BYTES` (default 8 GB, under Fargate's 20 GB
  default ephemeral storage which also holds the image). Beyond it → treated as "queue
  full" (503, spec edge case). Deleted after the job; a restart starts with a fresh `/tmp`
  in the container.

## R4 — Pacing LLM calls across all running checks

- **Decision**: one process-wide sliding-window limiter in `compliance_agent.py`: before
  each call, reserve `estimated_tokens = len(prompt) // 3 + 300` and one request slot
  within the last 60 s; wait (FIFO, via an `asyncio.Lock`) until both fit under 90 % of
  the limits; after the response, replace the estimate with `usage.total_tokens`. Limits
  start at 100 req / 100 k tokens and are updated from `x-ratelimit-limit-*` headers.
  The existing retry (429/5xx) stays as a safety net.
- **Rationale**: FR-011 / SC-005 — calls wait for quota instead of being sent and
  rejected. 90 % leaves headroom for a developer using the same key locally. ~3
  chars/token matches the measured ratio on code (conservative; corrected after each call).
- **Alternatives rejected**: reacting only to 429s with backoff (the "429 storm" the spec
  rules out: every running check retries at once); reading `x-ratelimit-remaining-*`
  only (remaining is per-response and races between concurrent calls).

## R5 — Fewer tokens per question

- **Finding**: the embedding model's tokenizer truncates at **128 tokens** (fastembed's
  `all-MiniLM-L6-v2`: `truncation.max_length = 128`) — each 4,000-char chunk is retrieved
  on roughly its first ~400 characters, yet all 4,000 are sent to the LLM.
- **Decision**: `MAX_CHUNK_CHARS` 4000 → 2000 and `TOP_K_CHUNKS` 5 → 4: at most 8,000
  chars per prompt instead of 20,000 (≈ −55 % prompt tokens, SC-007 ≥ 30 %). Smaller
  chunks are also represented better by their embedding (first ~400 of 2,000 chars
  instead of 4,000). Indexing cost roughly doubles (twice the chunks, each truncated to
  128 tokens) — acceptable now that indexing no longer races a request timeout.
- **Quality gate** (US4 AS2): run the reference projects (this repo's backend, the spec
  006 PDF + code pair, a code-only sample) before and after with `temperature: 0`;
  answers and escalations must match. If they don't, fall back to `TOP_K_CHUNKS = 3` with
  4,000-char chunks (−40 %, no indexing change) and re-run the gate.
- **Also**: send `temperature: 0` on every call — compliance answers should be
  reproducible, and it makes the quality gate meaningful (same input → same answer).

## R6 — Don't re-ask answered questions on resume

- **Decision**: the in-memory `ComplianceSession` gains `ai_answers: dict[field_id,
  answer]`. `run_compliance_check_with_index` takes that dict, reuses an entry instead of
  calling the LLM when a field has no human answer but was answered by the AI before, and
  adds new AI answers to it. Human answers still take precedence.
- **Rationale**: FR-010 / SC-006. Measured today: a resume re-sends every AI question
  (the `processed` dict starts empty on each run). Same code index + same question →
  the LLM would give the same answer anyway (especially at temperature 0), so reuse loses
  nothing.

## R7 — More checks in parallel on 2 vCPU / 8 GB

- **Decision**: one Chromium per process, launched lazily and relaunched if disconnected;
  each check runs in its own `browser.new_context()` (isolated cookies/storage — the
  checker keeps state per visitor) closed at the end. `MAX_CONCURRENT_CHECKS` default
  2 → 4. The embedding model's lazy init gets a `threading.Lock` (two indexing threads
  could otherwise load it twice).
- **Rationale**: FR-013 / SC-008. Per-check memory is then one renderer + page (~150–250
  MB) plus a small index, instead of a full browser process each; 4 × that fits easily in
  8 GB. Launch time (~1 s) is saved on every check. ONNX Runtime inference sessions are
  safe to call from several threads.
- **Alternatives rejected**: a pool of N browsers (more memory for no isolation gain over
  contexts); raising parallelism above 4 by default (CPU is 2 vCPU: indexing is
  CPU-bound, and the token ceiling makes more parallel checks just wait on the limiter).

## R8 — Restarts, failures, ownership

- **Decision**: on startup, `UPDATE analyses SET status='failed', error='…redémarrage…'
  WHERE status IN ('queued','running')` (FR-015). A job failure stores the
  `HTTPException.detail` (already user-facing French text) or a generic message for
  unexpected exceptions (logged with traceback) — FR-014. Status reads go through the
  existing owner-checked `GET /history/{id}` (FR-014 of spec 005 kept).
- **Session TTL during queue** (FR-009): a session with a resume waiting/running is marked
  `busy`; purge/expiry skip busy sessions, and the TTL restarts when the job ends.

## R9 — Limits

- `MAX_CONCURRENT_CHECKS=4`, `MAX_ACTIVE_CHECKS_PER_USER=2` (429 beyond),
  `MAX_QUEUED_CHECKS=50` and `MAX_QUEUED_UPLOAD_BYTES=8 GB` (503 beyond) — all env vars.
  12 users × 2 = 24 < 50, so the target scenario never hits the queue bound.
- Estimate: `ceil(position / MAX_CONCURRENT_CHECKS) × average duration`, the average being
  an exponential moving average of finished job durations (initial 60 s). Displayed as
  "environ".
