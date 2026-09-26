# Quickstart: Two-Stage Analysis

## Setup

Backend running with `ZAI_API_KEY` set; frontend running.

## Scenario: gap identified and resolved before form-filling

1. Upload a project with a clear purpose but no company/market context via the frontend.
2. Confirm the summary correctly describes the system's purpose, and `gaps` lists
   something like "no indication of EU market activity".
3. Type a direct answer for that gap (e.g. "Yes, sold in France and Germany") and submit.
4. Confirm the regenerated summary reflects the new information and that gap is gone
   from the list (or replaced by a more specific one, if the answer only partially
   resolved it).
5. Click "run" (start form-filling). Confirm the resulting `needs_human_input` does NOT
   include a question equivalent to the gap you already resolved.

## Scenario: uploading an extra document instead of typing

Repeat step 3 above but upload a short text file with the missing information instead of
typing. Confirm the same outcome (gap resolved, reflected in the regenerated summary).

## Scenario: proceeding with an unresolved gap

Skip resolving a gap and run form-filling anyway. Confirm the run still completes and
that the corresponding checker question, if reached, shows up in `needs_human_input`
(spec 003's existing fallback) — not silently guessed.

## Regression check

Run the existing spec 002/003 scenarios (`specs/002-rag-code-retrieval/quickstart.md`,
`specs/003-human-in-loop-answers/quickstart.md`) via `.../run` and `.../answer` to
confirm those flows still work end-to-end through the new endpoints.
