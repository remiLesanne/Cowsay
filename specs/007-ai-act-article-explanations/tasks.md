# Tasks: AI Act Article Explanations (guided RAG)

**Input**: Design documents from `specs/007-ai-act-article-explanations/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: no automated test tasks — team decision (manual validation via
[quickstart.md](quickstart.md)); offline sanity checks are part of the tasks below.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup — the corpus

- [ ] T001 Create `backend/scripts/build_ai_act_corpus.py` (stdlib `urllib` + `html.parser` only): download the EUR-Lex English HTML of Regulation (EU) 2024/1689, parse `art_N` blocks (title from `oj-sti-art`, paragraphs from `NNN.MMM` divs, points from table rows, chapter/section from the enclosing `cpt_X[.sct_N]`), annexes `anx_X` (title + one passage per top-level numbered item) and chapter/section titles + article lists; write `backend/data/ai_act_en.json` per data-model.md ("every article 1–113 and annex I–XIII present; passages in document order; `label` unique within its article/annex"); point passages carry their paragraph's intro sentence so they read standalone
- [ ] T002 Run the script, commit `backend/data/ai_act_en.json`, and sanity-check it: 113 articles, 13 annexes, `5(1)(a)`…`5(1)(h)` present, Annex III item 4 is employment, `cpt_III.sct_2` lists articles 8–15

---

## Phase 2: Foundational (blocks both stories)

- [ ] T003 Add `ArticleExplanation` model to `backend/db.py` (`analysis_id` UUID PK + FK → `analyses.id` ondelete cascade, `results_hash` char(64), `content` JSONB, `created_at`) — created by the existing `init_db()`/`create_all`, no migration
- [ ] T004 Create `backend/ai_act.py` corpus part: load `data/ai_act_en.json` once (module-level cache); `extract_references(results_text)` returning ordered, de-duplicated refs of kinds article (+ optional explicitly cited paragraph, from "Article 49 point 2" / "Article 6(2)"), annex, chapter/section; capped at 8 article/annex refs (citation order); offline-check it on real verdict strings ("see Article 5.", "Article 6 point 2a", "Article 49 point 2", "Chapter III Section 2", "Annex III")

---

## Phase 3: User Story 1 — Understand which articles apply and why (P1) 🎯 MVP

**Goal**: complete verdict → cited articles with selected official passages + French explanation.
**Independent test**: quickstart scenarios 1-3, 5.

- [ ] T005 [US1] In `backend/ai_act.py`, `select_passages(ref, query)`: rank the passages of that article/annex only by cosine similarity to the query using `code_index`'s fastembed model; keep top 3 (all if ≤ 3) + always the explicitly cited paragraph's passages; the query is the analysis's question/answer pairs (question text + chosen answers) plus the verdict
- [ ] T006 [US1] In `backend/ai_act.py`, `explain(analysis)`: build refs + passages, one Mistral call reusing `compliance_agent`'s HTTP client / `LLM_API_URL` / `LLM_MODEL` with `response_format: {"type": "json_object"}`; prompt = verdict + Q/A pairs + selected passages only, answer in French, per article `explanation` / `why_it_applies` / `what_it_implies`, must say when the passages don't settle which part applies; assemble the explanation set (data-model.md): `url` to the French official text (`…/FR/TXT/HTML/?uri=OJ:L_202401689#art_N` / `#anx_X` / `#cpt_X.sct_N`), chapter/section refs → `see_also` without AI, unknown refs → `available: false`; statuses `incomplete` / `no_references` / `ready`; Mistral errors → 502/504 like `compliance_agent`
- [ ] T007 [US1] Add `GET /api/v1/history/{analysis_id}/articles` to `backend/history.py`: owner check → 404 exactly like `get_analysis`; incomplete → `{"status": "incomplete", ...}` without AI call; else return the stored set if `results_hash` matches SHA-256 of the current `results_text`, otherwise generate, upsert the `ArticleExplanation` row, return it
- [ ] T008 [P] [US1] In `frontend/app/lib/api.ts`: types `ArticleExplanationSet` / `ExplainedArticle` / `SeeAlsoRef` and `getArticleExplanations(analysisId)` via `authFetch`
- [ ] T009 [US1] Create `frontend/app/components/ArticleExplanations.tsx`: loads on mount (props: `analysisId`, `isComplete`, `resultsText` so it reloads when the verdict changes after a resume); states loading ("Analyse des articles de l'AI Act…"), error + "Réessayer", incomplete ("Complétez le formulaire pour obtenir l'explication des articles"), no references; per article a card: ref + title, explanation, "Pourquoi ça vous concerne", "Ce que ça implique", collapsible official excerpts labelled "Extrait officiel (version anglaise)" with their labels, link "Texte officiel (FR) ↗"; "Voir aussi" list; a note that the checker's verdict is authoritative and explanations are an AI reading aid (FR-010); same visual style as the result page
- [ ] T010 [US1] Render `ArticleExplanations` in `frontend/app/analyse/page.tsx` right under the verdict card

**Checkpoint**: quickstart 1-3, 5 pass.

---

## Phase 4: User Story 2 — Instant on reopening (P2)

**Goal**: reuse stored explanations while the verdict is unchanged.
**Independent test**: quickstart scenario 4.

- [ ] T011 [US2] Verify end-to-end that a second call for the same verdict returns the stored set without a Mistral call (log line in `ai_act.explain` on each generation), and that a resume changing the verdict regenerates (hash mismatch) — fix `history.py` caching if not

---

## Phase 5: Polish & Cross-Cutting

- [ ] T012 Run all [quickstart.md](quickstart.md) scenarios; `npx tsc --noEmit`, `npm run lint`, `npm run build` in `frontend/`
- [ ] T013 [P] Update `README.md`: the guided-RAG feature and why guided, the endpoint, corpus source/licence/rebuild command, new table; in "Not done yet" replace the "cross-checking against the actual AI Act article text" item with what's done and what isn't (recitals, verdicts on incomplete forms)

---

## Dependencies & Execution Order

- T001 → T002 → (T003, T004) → T005 → T006 → T007 → T008–T010 → T011 → T012–T013.
- US2 is mostly delivered by T007's cache; T011 is its verification.

## Parallel Opportunities

- T003 and T004 (different files) once the corpus exists; T008 alongside T005–T007.

## Implementation Strategy

1. Corpus first (everything depends on its shape), then backend US1 checked with curl.
2. Frontend section, then cache verification, then docs.
3. One commit per phase on `feature/ai-act-article-explanations`; no merge into `main`
   without the user's OK (a push to `main` triggers the AWS deploy).
