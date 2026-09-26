# Quickstart: Validating Full-Codebase Analysis via Retrieval

## Prerequisites

- Backend running locally with `ZAI_API_KEY` set (see project README).
- New dependencies installed (added by this feature): `llama-index-core`,
  `llama-index-embeddings-huggingface` (see `plan.md` Technical Context).

## Setup: a project that would defeat today's fixed truncation

1. Create a small folder with N filler files before the relevant one, so the relevant
   fact sits past today's ~12,000-character truncation window, e.g.:
   ```text
   test-project/
   ├── filler_01.py ... filler_20.py   # innocuous code, no compliance-relevant content
   └── real_system.py                  # e.g. contains a biometric-identification function
   ```
2. Zip it: `Compress-Archive -Path test-project\* -DestinationPath test-project.zip`

## Run

```powershell
curl -X POST http://localhost:8000/api/v1/compliance-check `
  -F "file=@test-project.zip" `
  -F "company_name=Test Co"
```

## Expected outcome

- **Before this feature** (fixed truncation): the checker question about biometric
  identification is answered with low confidence and appears in `needs_human_input`,
  because `real_system.py`'s content never reached the LLM.
- **After this feature** (retrieval): that question is answered correctly (matching what
  a human filling the form with the same facts would answer) and does NOT appear in
  `needs_human_input`, because `real_system.py` is retrieved as relevant regardless of
  its position in the project.

## Regression check

Re-run the existing small test project from `specs/001-compliance-check-agent/spec.md`
(one that already fit within the old fixed window) and confirm `results_text` and
`needs_human_input` are unchanged from before this feature (SC-003: no regression).
