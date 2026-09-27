# Data Model: Concurrent Analyses

## Analysis (table `analyses`, existing — spec 005)

Now created **at submission**, before the check runs, and updated by the job.

| Field | Change | Notes |
|---|---|---|
| `status` | **new**, `VARCHAR(16) NOT NULL DEFAULT 'done'` | `queued` → `running` → `done` \| `failed`. Existing rows become `done` via the default. A resume moves a `done` analysis back to `queued`. |
| `error` | **new**, `TEXT NULL` | Plain-language failure reason (French), set only when `status = failed`. Cleared when a new run starts. |
| `started_at` | **new**, `TIMESTAMPTZ NULL` | When the current/last run left the queue. |
| `finished_at` | **new**, `TIMESTAMPTZ NULL` | When the current/last run ended (done or failed). |
| `content_fingerprint` | unchanged type | `''` until the first run has extracted the files (the fingerprint needs them). |
| `results_text` | default `''` | Empty until the first run finishes. |
| `is_complete` | default `false` | |
| `question_details`, `needs_human_input` | default `[]` | Previous values are kept while a resume is queued/running. |

Added at startup by the existing idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
block in `db.init_db` (no migration tool — same approach as `pdf_warning`).

### State transitions

```
submit ──► queued ──► running ──► done ──(resume)──► queued ...
              │           │
              │           └──► failed      (job error)
              └───────────────► failed      (server restart while queued/running)
```

A `failed` analysis is terminal: the user resubmits (the upload is not kept).

## Queued job (in memory — `backend/job_queue.py`)

| Field | Notes |
|---|---|
| `analysis_id` | The Analysis it updates. |
| `user_id` | For the per-user limit. |
| `kind` | `first_run` \| `resume`. |
| `payload` | first_run: temp file path of the upload (or none), its original name/extension, PDF text, company name/context. resume: session id. |
| `held_bytes` | Size of the temp upload, counted against `MAX_QUEUED_UPLOAD_BYTES`. |
| `enqueued_at` | For ordering and wait metrics. |

Lost on restart by design (see R8); the matching Analysis rows are marked failed at startup.

## ComplianceSession (in memory — `backend/session_store.py`, existing)

| Field | Change |
|---|---|
| `ai_answers` | **new**, `dict[field_id, answer]` — AI answers already given in this analysis, reused on resume (FR-010). |
| `busy` | **new**, `bool` — true while a resume for it is queued/running; expiry/purge skip it (FR-009). |
