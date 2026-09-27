# Data Model: User Accounts and Per-User Analysis History

## `users` (new table)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID, PK | generated |
| `email` | text, unique | stored lower-cased and trimmed; valid email syntax (FR-001) |
| `password_hash` | text | argon2 hash, never the password (FR-003) |
| `created_at` | timestamptz | set on insert |

## `analyses` (new table)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID, PK | generated; used in `/analyse?id=` |
| `user_id` | UUID, FK → `users.id`, indexed | owner; every read/resume filters on it (FR-014) |
| `filename` | text | uploaded file name |
| `content_fingerprint` | char(64), indexed | SHA-256 hex, see research.md (FR-009) |
| `company_name` | text, nullable | as submitted |
| `results_text` | text | checker verdict as scraped |
| `is_complete` | boolean | |
| `question_details` | JSONB | list of Question detail (below) |
| `needs_human_input` | JSONB | list of Pending question (spec 003 shape, unchanged) |
| `created_at` / `updated_at` | timestamptz | `updated_at` bumped on every resume round (FR-011) |

Not stored: uploaded files, Repomix text, embeddings (FR-009).

### Question detail (JSON element, also returned by the API — FR-010)

```json
{"field_id": "wsf-1-field-wrapper-57", "type": "radio",
 "question": "Entity type ...", "answer": ["Provider"],
 "reasoning": "...", "confidence": "high", "source": "ai"}
```

- `answer`: list of selected options for `radio`/`checkbox`, a string for text fields.
- `source`: `"ai"` or `"human"`. `confidence`: `high|medium|low` for AI, `human` for human.

## In-memory `ComplianceSession` (existing, `backend/session_store.py`) — extended

Adds `user_id` and `analysis_id`. `get_session` callers compare `user_id` with the
current user and treat a mismatch as not found (FR-014).

## Lifecycle

```text
POST compliance-check ──► check runs ──► INSERT analyses (+ session created)
POST .../{session}/answer ──► owner check ──► check re-runs ──► UPDATE same analyses row
check fails (LLM/site error) ──► nothing written; existing row keeps last good state
session expires (30 min) ──► row still readable; resume → 404 "re-upload"
```
