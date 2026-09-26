# Quickstart: Validating Accounts and History

## Prerequisites

- Local PostgreSQL with a `cowsay` database; `backend/.env` has `DATABASE_URL`,
  `JWT_SECRET` (any long random string: `python -c "import secrets;print(secrets.token_urlsafe(48))"`)
  and `MISTRAL_API_KEY`.
- Backend: `cd backend && .venv/bin/pip install -r requirements.txt && .venv/bin/uvicorn main:app --reload --port 8000`
  (tables are created on startup).
- Frontend: `cd frontend && npm run dev` → http://localhost:3000.
- A small test project zip (see the ones used in manual testing, e.g. `streamlit/llm-examples`).

## Scenarios (manual, in the browser)

1. **Guard** — open http://localhost:3000 logged out → redirected to `/login` (US1-5).
2. **Register** — create `alice@test.fr` / 8+ chars → logged in, email shown in header
   (US1-1). Register `ALICE@test.fr` again → refused "email déjà utilisé" (US1-2).
3. **Login errors** — wrong password and unknown email show the same message (US1-3).
4. **Saved check** — upload the zip → result page shows the verdict **and** the
   per-question table with source IA/humain (US2-1).
5. **Resume** — answer the pending question(s) → same analysis updated, answered
   question now listed with source "humain" (US2-2). If a text question shows up, its
   answer must not come back as pending (US2-3, bug fix).
6. **History** — open "Mes analyses" → the analysis is listed; open it → same verdict
   and detail, instantly, no new check in the backend logs (US3-1/2, SC-003).
7. **Isolation** — log out, register `bob@test.fr` → empty history (US3-4); paste
   Alice's `/analyse?id=...` URL → "introuvable" (US3-3, SC-004).
8. **Logout** — log out → back to `/login`; the home page is no longer reachable (US1-4).

## API spot checks (curl)

```bash
curl -s -X POST localhost:8000/api/v1/compliance-check -F file=@demo.zip   # → 401 (US2-4)
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"alice@test.fr","password":"..."}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8000/api/v1/history -H "Authorization: Bearer $TOKEN"
```

## Persistence check

Restart the backend → accounts and history still there; resuming a pre-restart
session returns the "re-upload" 404 while the analysis stays viewable (spec Edge Cases).
