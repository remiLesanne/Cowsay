# Research: AI Act Article Explanations (guided RAG)

## Decision: Guided retrieval — the checker picks the articles, similarity search only picks passages inside them

**Rationale**: Verified on the checker page itself: every verdict message cites its legal
basis explicitly ("see Article 5", "Under Article 6 your AI system is considered
'high-risk'", "Article 49 point 2", "Chapter III Section 2"). Those references are
extracted with a regular expression (deterministic, no AI). Similarity search is then run
over the passages of the cited articles only, with the analysis's questions + answers as
the query — its one job is choosing *which* passages of a long article matter (Article 5
has 8 prohibited practices; Annex III has 8 high-risk areas).

**Alternatives considered**: classic RAG over the whole regulation (rejected — can return
an article that sounds related but doesn't apply; see spec "Why guided"); no retrieval at
all, sending whole cited articles to the LLM (rejected — Articles 5/6/50 plus annexes blow
up prompt size, and the LLM then has to find the relevant point itself, less reliably and
less visibly than showing the selected passages).

## Decision: Corpus = EUR-Lex English OJ text, parsed once into a committed JSON file

**Rationale**: `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689`
(verified 2026-09-27: 200 OK, 1.26 MB) has stable ids — `art_N` per article, `NNN.MMM`
per paragraph, points `(a)…` in table rows, `anx_X` per annex, `cpt_X[.sct_N]` per
chapter/section. A one-off script (`backend/scripts/build_ai_act_corpus.py`, stdlib
`html.parser` only — no new runtime dependency) writes `backend/data/ai_act_en.json`;
the backend only reads that file (FR-002: no external site at request time).
English because the checker's questions/verdicts are English and the existing embedding
model (all-MiniLM-L6-v2) is English-only — French passages would retrieve poorly.
Explanations are generated in French; links point to the official French text
(`…/FR/TXT/HTML/?uri=OJ:L_202401689#art_N`).

**Alternatives considered**: artificialintelligenceact.eu per-article pages (unofficial
presentation, one request per article); French corpus (needs a multilingual embedding
model, a new ~200 MB download).

## Decision: Passage granularity = point when a paragraph has points, else paragraph

Article 5(1) is one paragraph with points (a)–(h): each point becomes its own passage
(prefixed by the paragraph's intro sentence so it reads standalone), labelled `5(1)(f)`.
Annexes are split per numbered item (Annex III `4.` = employment). Explicitly cited
paragraphs ("Article 49 point 2" → `49(2)`) are always included (FR-003).

## Decision: In-memory similarity over the cited passages only, reusing the existing embedding model

Only a few dozen passages per verdict, so they are embedded on demand with
`code_index`'s already-loaded fastembed model (no index persisted, no new model). Top 3
passages per article (all of them if the article has ≤ 3).

## Decision: One Mistral call per explanation set, JSON mode, grounded prompt

`mistral-small-latest` with `response_format: {"type": "json_object"}` returns one object
per article (`explanation`, `why_it_applies`, `what_it_implies`). The prompt contains the
verdict, the question/answer pairs, and the selected passages only, and instructs to say
so when the passages don't settle which part applies (FR-004 / Principle II). At most 8
references (citation order) keep the prompt under ~25k characters.

## Decision: New `article_explanations` table, keyed by analysis + verdict hash

A new table rather than a column on `analyses`: production (Neon) already has
`analyses`, and `create_all` creates missing tables but never alters existing ones — a
new table needs no migration. Stored with `results_hash` (SHA-256 of the verdict text):
same hash → reuse (US2), different hash → regenerate (FR-007).

## Decision: Separate endpoint, called by the result page after the verdict is shown

`GET /api/v1/history/{analysis_id}/articles` generates on first call and caches, so the
check itself is untouched (FR-008, SC-004) and reopening is instant (SC-003).
