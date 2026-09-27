# Quickstart: PDF Document Input

## Setup

Backend running with `MISTRAL_API_KEY` set (see README), `DATABASE_URL`/`JWT_SECRET`
configured (spec 005), frontend running, logged in.

## Scenario: PDF only, no code (User Story 1)

1. Find or create a short PDF describing a real or fictional AI system (purpose, who
   operates it, who it affects, what data it uses) — a public AI register entry works
   well.
2. On the compliance-check form, attach only the PDF (leave the code file empty).
3. Confirm the request succeeds (not rejected for missing a code file) and the result's
   `question_details` show answers grounded in facts from the PDF, with the same
   `needs_human_input` escalation behavior as a code-only run for anything the document
   doesn't cover.

## Scenario: code only, no PDF (User Story 2 — regression)

Run the existing one-shot flow exactly as before this feature (upload only a code
file/zip). Confirm the result is unchanged from pre-feature behavior — same fields, same
timing characteristics.

## Scenario: both PDF and code (User Story 3)

1. Prepare a code file and a PDF for the same fictional system, each containing a fact the
   other doesn't (e.g. the PDF states "operated by Acme Corp"; the code contains a comment
   or config value the PDF doesn't mention).
2. Submit both together.
3. Confirm the question answerable only from the PDF fact is answered correctly, and
   separately that the question answerable only from the code fact is also answered
   correctly — proving both sources are actually consulted.

## Scenario: neither PDF nor code (Edge Case / SC-004)

```powershell
curl -X POST http://localhost:8000/api/v1/compliance-check `
  -H "Authorization: Bearer <token>"
```
(no `file`, no `pdf` field at all)

Confirm: `400` response, immediate (no Repomix run, no browser launched, no LLM call).

## Scenario: PDF with no extractable text (FR-006, FR-006a, SC-005)

1. Create a PDF that's a scanned image or a screenshot saved as PDF (no real text layer —
   e.g. printing an image to PDF, not exporting text).
2. Submit it alone.
3. Confirm: the request still completes (not rejected outright), `pdf_warning` is present
   in the response stating no text could be extracted, and every question ends up in
   `needs_human_input` (there's nothing for the LLM to answer from) — the same outcome as
   any source with no usable content, not a special-cased failure.

## Scenario: PDF with some unreadable pages

Create a multi-page PDF where some pages are real text and others are pasted images with
no text layer. Submit alone or with code. Confirm `pdf_warning` reports the partial count
(e.g. "2 page(s) sur 5...") and that questions answerable from the readable pages are
still answered correctly.

## Scenario: invalid PDF upload

Rename a non-PDF file (e.g. a `.txt` or a corrupted file) to `.pdf` and submit it in the
PDF slot. Confirm a `400` "invalid PDF" error, no processing attempted.

## Regression check

Run the existing human-in-the-loop resume flow (`specs/003-human-in-loop-answers`) on a
check started from a PDF-only or PDF+code submission — confirm resume behaves identically
to a code-only session (the combined text was already baked into the cached
`ProjectIndex` at session creation, so nothing PDF-specific needs to happen on resume).
