# Data Model & API Changes: Two-Stage Analysis

## ProjectSummary

| Field | Type | Notes |
|---|---|---|
| `summary` | string | Coherent prose description of the system for AI Act purposes. |
| `gaps` | InformationGap[] | What the summary couldn't determine. |

## InformationGap

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable slug (e.g. `"eu-market-activity"`) so a resolution can reference it. |
| `description` | string | Human-readable: what's missing and why it matters. |

## ComplianceSession (extends spec 003's session)

| Field | Type | Notes |
|---|---|---|
| `code_context` | string | The Repomix representation — kept so `resolve-gaps` can re-summarize. |
| `extra_documents` | string[] | Text of any additional documents uploaded to resolve gaps, appended to the summarization prompt each time. |
| `summary` | ProjectSummary | Current summary/gaps; replaced (not merged) on each `resolve-gaps` call. |
| *(existing spec 003 fields unchanged: `project_index`, `human_answers`, `unresolved_by_field_id`, `expires_at`)* |

## API Changes

### `POST /api/v1/compliance-check/analyze` (new; replaces the old direct-run entry point)

Multipart form: `file`, optional `company_name`, `company_context`. Runs Repomix +
one summarization call. Response:
```json
{
  "session_id": "...",
  "summary": "This system appears to ...",
  "gaps": [
    {"id": "eu-market-activity", "description": "The code doesn't indicate whether this system is placed on the EU market."}
  ]
}
```

### `POST /api/v1/compliance-check/{session_id}/resolve-gaps` (new)

Either JSON `{"answers": [{"gap_id": "...", "text": "..."}]}` or a multipart upload with
an additional `file`. Merges into the session's context, regenerates the summary.
Response: same shape as `analyze` (updated `summary`/`gaps`, same `session_id`).

### `POST /api/v1/compliance-check/{session_id}/run` (new)

No body required (uses the session's current summary + accumulated gap answers as
context). Runs the Playwright form-filling loop. Response: same shape as spec 002/003's
original `compliance-check` response (`is_complete`, `results_text`,
`questions_answered`, `needs_human_input`, `session_id`).

### `POST /api/v1/compliance-check/{session_id}/answer` (spec 003, unchanged)

Still the fallback for any `needs_human_input` question `run` produces.
