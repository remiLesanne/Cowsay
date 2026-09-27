# API Contract: AI Act Article Explanations

### 🔒 `GET /api/v1/history/{analysis_id}/articles`

Requires `Authorization: Bearer <token>` (spec 005).

- `200` — explanation set (see data-model.md), one of:
  - `{"status": "incomplete", "articles": [], "see_also": []}` — form not complete, nothing generated.
  - `{"status": "no_references", "articles": [], "see_also": []}` — verdict cites nothing.
  - `{"status": "ready", "articles": [...], "see_also": [...]}` — from cache if the stored
    `results_hash` matches the current verdict, otherwise generated then stored.
- `404` — analysis unknown or owned by another user (same message as spec 005).
- `502` / `504` — AI call failed / timed out (existing `compliance_agent` error style);
  nothing is stored, the client may retry.

No other endpoint changes; the compliance check responses are untouched (FR-008).
