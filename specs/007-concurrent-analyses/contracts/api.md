# API Contract Changes: Concurrent Analyses

All routes below require `Authorization: Bearer <token>` (unchanged). Error bodies keep the
existing `{"detail": ...}` shape.

## `POST /api/v1/compliance-check` — now asynchronous

Request: unchanged (multipart `file` and/or `pdf`, optional `company_name`,
`company_context`).

**202 Accepted**
```json
{
  "analysis_id": "uuid",
  "status": "queued",
  "queue_position": 3,
  "estimated_wait_seconds": 120,
  "filename": "app.zip + register.pdf",
  "pdf_warning": "…"            // only when applicable (spec 006)
}
```
`queue_position` is 1-based among waiting analyses (`0` if it started immediately).
No `session_id` yet: it appears on `GET /history/{id}` once the run is `done`.

Errors (all returned before anything is queued):
- `400` / `413` — unchanged validation errors (missing file, format, size, invalid zip
  or PDF, dangerous path, too many files).
- `429` — `"Vous avez déjà 2 analyses en cours ou en attente, merci d’attendre qu’une se termine"`.
- `503` — queue full: `"La plateforme est saturée, merci de réessayer dans quelques minutes"`.

## `POST /api/v1/compliance-check/{session_id}/answer` — now asynchronous

Request: unchanged (`{"answers": [{"field_id", "value"}]}`).

**202 Accepted**
```json
{"analysis_id": "uuid", "session_id": "…", "status": "queued",
 "queue_position": 0, "estimated_wait_seconds": 0}
```
Errors: `400` invalid option (unchanged), `404` unknown/expired/other user's session
(unchanged), `409` a resume for this analysis is already queued or running, `429` / `503`
as above.

## `GET /api/v1/history/{analysis_id}` — adds status fields

Adds to the existing body:
```json
{
  "status": "queued | running | done | failed",
  "error": "…" | null,
  "queue_position": 2 | null,            // only while queued
  "estimated_wait_seconds": 60 | null,   // only while queued
  "started_at": "…" | null,
  "finished_at": "…" | null
}
```
`session_id` is returned only when no run is queued/running (`done`, or `failed` after a
resume — so a failed resume can be retried) and the session is still alive. Polled by
the frontend every 3 s while `status` is `queued` or `running`.

## `GET /api/v1/history` — adds `status`

Each item gains `"status"`.

## `POST /api/v1/analyses` (Repomix only, unused by the UI)

Unchanged and still synchronous; keeps its own small concurrency guard (`503` when busy),
separate from the analysis queue.
