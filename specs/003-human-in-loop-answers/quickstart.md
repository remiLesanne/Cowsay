# Quickstart: Human-in-the-Loop Answers

## Setup

Same as `specs/002-rag-code-retrieval/quickstart.md` — backend running with
`ZAI_API_KEY` set, frontend running.

## Scenario: answer an unresolved question

1. Upload a project whose entity type isn't obvious from the code (e.g. a plain web app
   with no AI system) via `http://localhost:3000`.
2. Confirm the result shows "Entity type" as unresolved, with a `session_id` and the
   options (`Provider`, `Deployer`, `Distributor`, `Importer`, `Product manufacturer`,
   `Authorised representative`) rendered as clickable choices, not a text box.
3. Pick one (e.g. "Provider") and submit.
4. Confirm:
   - No file re-upload happened (only the answer was sent).
   - The response's `needs_human_input` no longer lists "Entity type".
   - The response may show new unresolved questions (expected — answering one question
     can reveal others) or a final recommendation.

## Scenario: reject an invalid answer

```powershell
curl -X POST http://localhost:8000/api/v1/compliance-check/<session_id>/answer `
  -H "Content-Type: application/json" `
  -d '{"answers":[{"field_id":"wsf-1-field-57-row-1","value":"provider"}]}'
```
(lowercase `"provider"` — not an exact match to the real option `"Provider"`)

Confirm: `400` response, no multi-second wait (no browser launched), and the error names
the question and lists the real valid options.

## Scenario: expired session

Wait past the TTL (or manually clear the session cache), then submit an answer to that
`session_id`. Confirm a clear `404`-style error telling the caller to re-upload, not a
silent empty/wrong result.

## Regression check

Run the original one-shot flow from `specs/002-rag-code-retrieval/quickstart.md`
unmodified; confirm it still works exactly as before (this feature is additive).
