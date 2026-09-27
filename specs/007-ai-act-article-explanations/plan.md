# Implementation Plan: AI Act Article Explanations (guided RAG)

**Branch**: `feature/ai-act-article-explanations` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-ai-act-article-explanations/spec.md`

## Summary

For a complete analysis, extract the article/annex/chapter references from the checker's
verdict (regex), look them up in a committed JSON copy of the official AI Act (EUR-Lex,
English), rank each cited article's passages by similarity to the analysis's
question/answer pairs (existing fastembed model, in memory), and ask Mistral once for a
French explanation per article grounded only in the selected passages. Served by a new
owner-only endpoint, cached per verdict in a new table, displayed as a section of the
result page loaded after the verdict.

## Technical Context

**Language/Version**: Python 3.11/3.12 backend; TypeScript, Next.js 16.3, React 19 frontend

**Primary Dependencies**: existing only — FastAPI, SQLAlchemy, httpx (Mistral),
llama-index fastembed model from `code_index.py`; corpus build script uses stdlib
`html.parser` + `urllib` (no new dependency)

**Storage**: new PostgreSQL table `article_explanations` (created by `create_all`, no
migration); static corpus file `backend/data/ai_act_en.json`

**Testing**: manual per team decision — [quickstart.md](quickstart.md); offline sanity
checks of corpus + reference extraction during implementation

**Target Platform**: Linux server (ECS) + browser (Vercel) — same as today

**Project Type**: web application (existing `backend/` + `frontend/`)

**Performance Goals**: first explanation ≤ 15s, cached ≤ 2s (SC-003); check duration
unchanged (SC-004)

**Constraints**: only cited articles (SC-001); grounded, non-guessing prompt (FR-004);
no external site at request time (FR-002); prompt ≤ ~25k chars (≤ 8 references × top-3
passages)

**Scale/Scope**: 1 new backend module, 1 script, 1 data file, 1 table, 1 endpoint, 1
frontend section

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status |
|---|---|
| I. Drive the real tool | ✅ The checker's verdict stays authoritative and decides which articles apply; explanations only annotate it, labelled as an AI reading aid (FR-010). |
| II. No silent guessing | ✅ Explanations grounded only in the selected official passages; the prompt requires saying when the passages don't settle which part applies; incomplete forms get no explanation. |
| III. Spec-driven | ✅ `specs/007-ai-act-article-explanations/`. |
| IV. Production-shaped | ✅ No runtime dependency on an external site; new table instead of an ALTER on the live Neon schema; bounded prompt size; owner-only endpoint. |
| V. Docs current | ✅ README task (feature, endpoint, corpus rebuild, status: closes "cross-checking against the actual AI Act article text"). |

Post-design re-check: no violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-ai-act-article-explanations/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/api.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── scripts/build_ai_act_corpus.py  # NEW: one-off EUR-Lex HTML → data/ai_act_en.json (stdlib only)
├── data/ai_act_en.json             # NEW: committed corpus
├── ai_act.py                       # NEW: corpus loading, reference extraction, passage
│                                   #      ranking, Mistral explanation, cache read/write
├── db.py                           # CHANGED: ArticleExplanation model
├── history.py                      # CHANGED: GET /api/v1/history/{id}/articles
└── compliance_agent.py             # unchanged (its HTTP client / LLM settings are reused)

frontend/app/
├── lib/api.ts                      # CHANGED: getArticleExplanations(id) + types
├── components/ArticleExplanations.tsx # NEW: the "Articles de l'AI Act concernés" section
└── analyse/page.tsx                # CHANGED: renders the section under the verdict
```

**Structure Decision**: same flat backend layout as specs 002–006 (one module per
concern); the corpus builder goes in `backend/scripts/` since it is a dev tool, not part
of the request path. Frontend section extracted into its own component to keep
`analyse/page.tsx` readable.
