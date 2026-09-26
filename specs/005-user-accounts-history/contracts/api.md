# API Contract: Accounts and History

All authenticated routes require `Authorization: Bearer <token>`; missing, invalid or
expired token → `401 {"detail": "..."}`.

## Auth (new)

### `POST /api/v1/auth/register`
Body `{"email": "a@b.fr", "password": "min 8 chars"}` →
`201 {"access_token": "...", "token_type": "bearer", "user": {"id", "email"}}`
(registering logs the user in). `409` email already used (case-insensitive), `422`
malformed email / password too short.

### `POST /api/v1/auth/login`
Body `{"email", "password"}` → `200` same shape as register. `401` with one generic
message for unknown email **or** wrong password (FR-002).

### `GET /api/v1/auth/me` 🔒
→ `200 {"id", "email", "created_at"}`.

## Compliance check (existing, changed)

### `POST /api/v1/compliance-check` 🔒 (was public)
Same multipart input. Response gains `analysis_id` and `question_details`:
```json
{"session_id": "...", "analysis_id": "...", "filename": "...", "file_count": 3,
 "is_complete": false, "results_text": "...", "questions_answered": 2,
 "question_details": [ /* see data-model.md */ ], "needs_human_input": [ ... ]}
```

### `POST /api/v1/compliance-check/{session_id}/answer` 🔒
Same body. `404` if the session is unknown, expired **or owned by another user**.
Free-text answers are now applied (bug fix). Response: same shape as above; the same
`analysis_id` is updated.

## History (new)

### `GET /api/v1/history` 🔒
→ `200 [{"id", "filename", "company_name", "is_complete", "created_at", "updated_at"}]`,
current user's analyses only, newest first (`created_at` desc).

### `GET /api/v1/history/{analysis_id}` 🔒
→ `200` full saved analysis: the compliance-check response fields (without
`session_id`) plus `created_at`, `updated_at`, `content_fingerprint`, and
`session_id` **only if** its in-memory session is still alive (so the UI knows whether
pending questions can be answered in place). `404` if unknown or not owned by the user.

## Unchanged
`POST /api/v1/analyses` (Repomix only, unused by the UI) and `GET /health` stay public.
