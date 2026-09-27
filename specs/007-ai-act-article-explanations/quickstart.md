# Quickstart: Validating AI Act Article Explanations

## Prerequisites

- Spec 005 setup (Postgres, `DATABASE_URL`, `JWT_SECRET`, `MISTRAL_API_KEY`), backend and
  frontend running (`uvicorn main:app --reload --port 8000`, `npm run dev`).
- Corpus present: `backend/data/ai_act_en.json` (committed). To rebuild it:
  `cd backend && .venv/bin/python scripts/build_ai_act_corpus.py`.
- Test zips from manual testing: facial emotion recognition
  (`shrimantasatpati/Facial-Emotion-Recognition-DeepFace-StreamLit`), resume screening
  (`312323205202/ai-resume-screening-system`), `streamlit/llm-examples`.

## Scenarios (browser)

1. **Prohibited** — analyze the emotion-recognition zip; answer pending questions so that
   it is used in a workplace/education setting, until the form is complete. The result
   page shows "Articles de l'AI Act concernés" with **Article 5**, passage **5(1)(f)**
   among the excerpts, a French explanation that mentions the answers, and a link to the
   French official text (US1-1, SC-002).
2. **High-risk** — analyze the resume-screening zip to completion; Article 6 and
   Annex III appear, Annex III's employment item (4) among the passages; any explicitly
   cited paragraph ("Article N point X") is shown (US1-2/3). A "Chapter III Section 2"
   citation appears under "Voir aussi", without AI explanation (US1-4).
3. **Only cited articles** — compare the listed references with the verdict text: same
   set, same order, nothing extra (SC-001).
4. **Cache** — reload the page / reopen from "Mes analyses": explanations appear at once,
   no new Mistral call in the backend logs (US2-1, SC-003).
5. **Incomplete** — open an incomplete analysis: the section asks to complete the form,
   no AI call (Edge Cases).
6. **Isolation** — call the endpoint with another account's token → `404` (FR-009).

## API spot check

```bash
curl -s localhost:8000/api/v1/history/<analysis_id>/articles -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -40
```

## Offline checks (no AI call)

- Corpus: 113 articles, 13 annexes; `5(1)(a)`…`5(1)(h)` present.
- Reference extraction on real verdict strings: "see Article 5." → `Article 5`;
  "Article 49 point 2" → `Article 49` + paragraph 2; "Chapter III Section 2" → see-also.
