# Data Model & API Changes: Human-in-the-Loop Answers

## ComplianceSession (new, server-side, in-memory)

| Field | Type | Notes |
|---|---|---|
| `session_id` | string (UUID) | Returned to the caller on the first `/compliance-check` call. |
| `project_index` | `ProjectIndex` (spec 002) | Built once, reused on every resume round. |
| `human_answers` | dict[field_id, str \| list[str]] | Accumulated across rounds; merged with new answers on each resume call. |
| `expires_at` | timestamp | Now + TTL (30 min), refreshed on each access. |

**Validation rules**: a session not found or past `expires_at` MUST produce a clear error
(`404`-style "session expired or not found, please re-upload"), never a silent empty
result (FR-007).

## UnresolvedQuestion (extends `needs_human_input` entries from spec 001/002)

| Field | Type | Notes |
|---|---|---|
| `field_id` | string | The checker form's own DOM field id (stable across runs, per spec 002 `code_index`/`compliance_agent` design — see spec 001 Assumptions on the site's structure being stable). |
| `question` | string | Unchanged from before. |
| `reasoning` | string | Unchanged from before. |
| `type` | `"radio" \| "checkbox" \| "text"` | New. |
| `options` | string[] \| absent | New; present only for `radio`/`checkbox`. |

## HumanAnswer (submitted by the caller)

| Field | Type | Notes |
|---|---|---|
| `field_id` | string | Must match an `UnresolvedQuestion.field_id` from a prior result for validation to apply; an unknown id is accepted but has no effect (edge case in spec.md). |
| `value` | string \| string[] | string for `text`/`radio`; string[] for `checkbox`. |

**Validation rules**: for a `field_id` whose cached `UnresolvedQuestion.type` is
`radio`/`checkbox`, every submitted value MUST be a member of that question's `options`
(case-sensitive exact match, matching how `compliance_agent.py` already compares
option values case-insensitively via `_strip_html(...).strip().lower()` — reuse that
same normalization for the validation check so the two don't disagree). A mismatch
rejects the whole resume request (not just that one field) with the invalid field's
question + valid options in the error, per FR-003.

## API Changes

### `POST /api/v1/compliance-check` (existing endpoint, response extended)

Response gains `session_id`; `needs_human_input` entries gain `field_id`/`type`/`options`
per above. No breaking change to existing fields.

### `POST /api/v1/compliance-check/{session_id}/answer` (new)

Request body (JSON):
```json
{ "answers": [ { "field_id": "wsf-1-field-57-row-1", "value": "Provider" } ] }
```

Response: same shape as the original endpoint's response (`is_complete`, `results_text`,
`questions_answered`, `needs_human_input`, `session_id` — same session id, reusable for
further rounds).

Errors:
- `400` — an answer's value isn't among its question's valid options (includes the
  question and valid options in `detail`).
- `404` — `session_id` unknown or expired.
