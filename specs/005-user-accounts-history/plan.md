# Implementation Plan: User Accounts and Per-User Analysis History

**Branch**: `feature/user-accounts-history` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-user-accounts-history/spec.md`

## Summary

Add email/password accounts (backend-owned, JWT bearer) and make the compliance check
require a logged-in user. Every check round is persisted to PostgreSQL as one
`analyses` row per check (created on the first run, updated on each resume), including
the per-question detail the agent already computes but currently discards. A "Mes
analyses" page lists the user's analyses; `/analyse?id=` reloads any of them from the
database. Also fixes free-text human answers being dropped on resume.

## Technical Context

**Language/Version**: Python 3.11 (Docker) / 3.12 (local dev); TypeScript, Next.js 16.3, React 19

**Primary Dependencies**: existing FastAPI stack + new `sqlalchemy>=2`, `psycopg[binary]>=3`,
`pwdlib[argon2]`, `pyjwt`, `email-validator` (for pydantic `EmailStr`)

**Storage**: PostgreSQL 16 via `DATABASE_URL` (local now, Supabase/Neon later); in-memory
`session_store` unchanged for resumable sessions

**Testing**: manual, per team decision — scenarios in [quickstart.md](quickstart.md) plus curl
spot checks; no automated suite in scope

**Target Platform**: Linux server (Docker/ECS) + browser (Vercel)

**Project Type**: web application (existing `backend/` + `frontend/`)

**Performance Goals**: saving adds < 1s to a ~7-10s check (SC-006); history detail < 2s (SC-003)

**Constraints**: never store uploaded code (FR-009); secrets only via env (`JWT_SECRET`,
`DATABASE_URL`); cross-origin front/back (bearer header, not cookies — research.md)

**Scale/Scope**: school-project scale (tens of users); 2 new tables, 5 new/changed endpoints,
3 new pages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status |
|---|---|
| I. Drive the real tool | ✅ Checker automation untouched; only its output is persisted. |
| II. No silent guessing | ✅ Strengthened: the text-answer fix stops a human answer from being silently replaced by a new LLM guess. |
| III. Spec-driven | ✅ spec → plan → tasks trail in `specs/005-user-accounts-history/`. |
| IV. Production-shaped | ✅ Hashed passwords, secrets in env, ownership enforced server-side, `DATABASE_URL` switchable to managed Postgres. Accepted trade-offs (client-side logout, `localStorage` token, `create_all` instead of migrations) documented in research.md. |
| V. Docs current | ✅ README update is a task (endpoints, env vars, status). Constitution's stale "Z.AI" tech constraint flagged for a PATCH amendment, not blocking. |

Post-design re-check: no violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-user-accounts-history/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/api.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── db.py               # NEW: engine/session from DATABASE_URL, Base, User + Analysis models, init_db()
├── auth.py             # NEW: hashing, JWT encode/decode, get_current_user dependency, /auth router
├── history.py          # NEW: /history router (list + detail, owner-filtered)
├── main.py             # CHANGED: startup init_db, auth on compliance routes, save/update analysis,
│                       #          fingerprint, text-answer bug fix, include routers
├── compliance_agent.py # CHANGED: return question_details (field, answer, reasoning, source)
├── session_store.py    # CHANGED: session carries user_id + analysis_id; lookup by analysis_id
├── requirements.txt    # CHANGED: new deps
└── .env.example        # CHANGED: DATABASE_URL (placeholder), JWT_SECRET

frontend/app/
├── lib/api.ts          # CHANGED: token storage, authenticated fetch (401 → /login), auth/history calls
├── components/AppHeader.tsx   # NEW: logo, "Mes analyses", user email, logout
├── components/useRequireAuth.ts # NEW: client guard (calls /auth/me, redirects to /login)
├── login/page.tsx      # NEW
├── register/page.tsx   # NEW
├── historique/page.tsx # NEW: list
├── page.tsx            # CHANGED: guarded, header, navigates to /analyse?id=
├── analyse/page.tsx    # CHANGED: loads by ?id= from API, per-question table, expired-session message
└── compliance/page.tsx # CHANGED: uses authenticated fetch
```

**Structure Decision**: keep the existing flat `backend/` module layout (one module per
concern, as `code_index.py`/`session_store.py` already do) rather than introducing a
`src/models/services` tree for three new modules. Frontend keeps the App Router layout;
shared UI goes in `app/components/`.
