# Research: User Accounts and Per-User Analysis History

## Decision: Auth implemented in the FastAPI backend (email + password, JWT bearer)

**Rationale**: The backend is the only component that must enforce "logged in to run a
check" and "only your own analyses" (FR-006, FR-014) — an API caller bypassing the UI
(curl) must get the same protection, same reasoning as spec 003's server-side answer
validation. Owning auth in the backend keeps one source of truth, no new external
service or account, and works identically locally and once deployed.

**Alternatives considered**: Supabase Auth (managed, but needs a Supabase project/keys
the team doesn't have yet, plus token verification in the backend anyway); Auth.js in
Next.js (session lives in the frontend, backend would still need to verify it — two
auth systems for one feature).

## Decision: Stateless JWT (HS256, 24h) in an `Authorization: Bearer` header, stored in `localStorage`

**Rationale**: Frontend (Vercel) and backend (AWS) live on different origins in
production. Cross-site cookies would need `SameSite=None; Secure` + HTTPS on the
backend (which isn't in place, see README deployment notes); a bearer header works
across origins with the existing CORS setup. 24h expiry satisfies FR-005.

**Trade-offs accepted**: logout is client-side (the token is discarded; it stays
technically valid until expiry — no server-side revocation list). `localStorage` is
readable by injected scripts (XSS); acceptable for this scope, the app renders no
user-supplied HTML. Both documented in README.

**Alternatives considered**: server-side session table (revocable, but one more table
and a DB hit per request for no requirement asking for revocation); httpOnly cookies
(better XSS posture, blocked by the cross-origin/HTTPS constraint above).

## Decision: `pwdlib[argon2]` for password hashing, `PyJWT` for tokens

**Rationale**: FastAPI's current security docs use exactly this pair; `passlib` is
unmaintained and breaks with recent `bcrypt`. Argon2 satisfies FR-003.

## Decision: SQLAlchemy 2.0 (sync) + psycopg 3, tables created at startup

**Rationale**: `DATABASE_URL` (`postgresql+psycopg://…`) points at local PostgreSQL 16
today and Supabase/Neon later without code change (README target architecture).
Queries are tiny (one row insert/update per check round, one list per history view),
so a sync session inside the async endpoints costs milliseconds — negligible next to a
~7-10s check (SC-006). `Base.metadata.create_all()` at startup instead of Alembic: two
new tables, no existing data to migrate.

**Alternatives considered**: async SQLAlchemy/asyncpg (more moving parts, no measurable
gain at this volume); SQLModel (thin extra layer, not needed); Alembic (worth it at the
first schema change on data that must be preserved — flagged, not needed yet).

## Decision: Fingerprint = SHA-256 over the sorted (relative path, file bytes) of the extracted project

**Rationale**: FR-009 forbids storing code; the fingerprint must identify "same project"
(spec Assumptions). Hashing the uploaded zip bytes would differ for identical code
zipped twice (zip entries carry timestamps); hashing the extracted, filtered files
(same `IGNORED_ARCHIVE_DIRECTORIES` rules) in sorted path order is content-based and
independent of the Repomix version.

## Decision: History read from the database, resume still needs the in-memory session

**Rationale**: The analysis record is persisted (FR-007/013); the `ProjectIndex`
(embeddings) stays in `session_store` for 30 min as in spec 003 — persisting it would
contradict FR-009 (it contains code chunks). The session now carries `user_id` and
`analysis_id` so a resume both checks ownership (FR-014) and updates the right row
(FR-011).

## Decision: `/analyse?id=<analysis_id>` always loads the result from the API

**Rationale**: One screen for "just finished", "resumed" and "reopened from history"
(FR-013). Replaces the current `sessionStorage` hand-off between pages, so a reload or
a history link shows the same saved state.

## Bug root cause: free-text human answers dropped

`backend/main.py` `answer_compliance_check` does `continue` for any unresolved field
whose type isn't `radio`/`checkbox` *before* storing the answer in
`session.human_answers`, so text answers are never applied and the LLM is asked again.
Fix: validate only multiple-choice types, but store every answer for a known field.
