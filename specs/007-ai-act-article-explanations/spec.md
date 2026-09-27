# Feature Specification: AI Act Article Explanations (guided RAG)

**Feature Branch**: `feature/ai-act-article-explanations`

**Created**: 2026-09-27

**Status**: Draft

**Input**: User description: "A RAG that details the form results by pulling out the AI
Act articles the result refers to and explaining them according to the answers."
Design decided with the user: a *guided* RAG — the official checker's verdict decides
which articles apply (it already cites them, e.g. "Your system may be prohibited under
the EU AI Act. For more information see Article 5."); retrieval only searches *inside*
those articles for the paragraphs matching the user's answers (e.g. which of Article 5's
eight prohibited practices), and the AI explains them from that official text only.

## Why guided rather than classic RAG

A classic RAG searches the whole regulation by similarity to the answers and can surface
an article that merely *sounds* related — presented confidently, that is a wrong legal
statement. The checker already did the legal reasoning (constitution Principle I: drive
the real tool); what it doesn't say is *which part* of a long article applies and *what
it means* for this system. That is the gap this feature fills, and the only place where
similarity search is used.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Understand which articles apply and why (Priority: P1)

A user whose analysis is complete opens its result page. Below the checker's verdict, a
section "Articles de l'AI Act concernés" lists every article or annex the verdict refers
to. For each one: its number and title, the specific official passages that match the
user's situation, and a plain-French explanation of why it applies given their answers
and what it concretely implies — with a link to the official text.

**Why this priority**: This is the whole feature: the checker's verdict is a one-line
pointer ("see Article 5"); a user can't act on it without knowing which obligation or
prohibition it means for them.

**Independent Test**: Run the facial-emotion-recognition test project to a complete
"prohibited" verdict; confirm Article 5 is listed, the excerpt shown is the emotion
recognition prohibition (point (f)) rather than an unrelated point, and the explanation
refers to the user's actual answers.

**Acceptance Scenarios**:

1. **Given** a complete analysis whose verdict cites "Article 5", **When** the user opens
   the result page, **Then** Article 5 is listed with its title, the passage(s) matching
   the answers, an explanation in French, and a link to the official text.
2. **Given** a verdict citing a specific paragraph (e.g. "Article 6 point 2a"), **When**
   explanations are produced, **Then** that paragraph is always among the passages shown.
3. **Given** a verdict citing several articles and annexes, **When** the section is shown,
   **Then** each cited article/annex appears once, in the order the verdict cites them.
4. **Given** a verdict citing a whole chapter or section (e.g. "Chapter III Section 2"),
   **When** the section is shown, **Then** it appears as a "see also" entry with its title,
   the articles it contains, and a link — not as an AI explanation.

---

### User Story 2 - Explanations come back instantly once produced (Priority: P2)

A user reopens a complete analysis from "Mes analyses". The article explanations appear
immediately, without waiting for the AI again, unless the verdict changed since they
were produced (e.g. after answering more questions).

**Why this priority**: History (spec 005) promises instant reopening; producing
explanations again on every visit would also spend AI calls for nothing.

**Independent Test**: Open a complete analysis (explanations generated), reload the page
and reopen it from history; confirm the explanations appear at once and the backend
logs show no new AI call.

**Acceptance Scenarios**:

1. **Given** explanations already produced for the current verdict, **When** the analysis
   is reopened, **Then** they are shown without a new AI call.
2. **Given** an analysis whose verdict changed after a resume round, **When** it is
   opened, **Then** explanations are produced again for the new verdict.

### Edge Cases

- **Form incomplete**: no explanation is produced; the section says the form must be
  completed first (explaining a non-final verdict would be misleading).
- **Verdict cites no article**: the section says so; nothing is invented.
- **Cited article unknown to the stored text** (e.g. a typo on the checker's side): it is
  listed with a note that its text is unavailable, without an explanation.
- **AI service unavailable**: the verdict and question detail remain visible; the section
  shows an error with a retry option; nothing wrong is saved.
- **Another user's analysis**: refused as not found (same rule as spec 005).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST identify the article, annex and chapter/section references in
  the checker's verdict text of a complete analysis, and only those.
- **FR-002**: System MUST hold the official AI Act text (Regulation (EU) 2024/1689),
  split into articles/annexes and their paragraphs/points, with titles and chapter
  structure, and serve it without depending on an external site at request time.
- **FR-003**: For each cited article or annex, System MUST select the passages most
  relevant to the analysis's answers, searching **only within that article or annex**;
  a paragraph cited explicitly by the verdict MUST always be included.
- **FR-004**: System MUST generate, per cited article/annex, a French explanation of why
  it applies given the answers and what it implies, grounded **only** in the selected
  official passages; when the passages don't settle which part applies, the explanation
  MUST say so rather than guess (constitution Principle II).
- **FR-005**: The result page MUST show, per cited article/annex: reference, title,
  selected official passages (marked as the official English text), the explanation, and
  a link to the official French text.
- **FR-006**: Chapter/section references MUST be shown as "see also" entries (title,
  contained articles, link) without AI explanation.
- **FR-007**: Explanations MUST be stored per analysis and reused while the verdict is
  unchanged; a changed verdict MUST trigger new explanations.
- **FR-008**: Producing explanations MUST NOT delay the compliance check itself; the
  verdict is shown first and explanations load afterwards.
- **FR-009**: Only the owner of an analysis can obtain its explanations.
- **FR-010**: The interface MUST state that the checker's verdict is authoritative and
  that explanations are an AI-generated reading aid.

### Key Entities

- **AI Act corpus**: the regulation's articles and annexes, each with number, title,
  chapter/section, and ordered passages (paragraph or point, with its label such as
  "5(1)(f)" and text). Static, versioned with the code, with its source and date.
- **Article explanation set**: for one analysis and one verdict version — the list of
  explained articles/annexes (reference, title, link, selected passages, explanation,
  why it applies, what it implies) and "see also" entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the test projects used in manual testing, 100% of the articles/annexes
  cited by a complete verdict appear in the section, and no article that isn't cited
  does.
- **SC-002**: For the emotion-recognition test project with a workplace/education
  answer, the emotion-recognition prohibition is among the passages shown for Article 5.
- **SC-003**: Explanations appear within 15 seconds of opening a complete result the
  first time, and within 2 seconds on later visits.
- **SC-004**: The compliance check duration is unchanged by this feature.

## Assumptions

- Official text taken from EUR-Lex (English consolidated OJ version of Regulation (EU)
  2024/1689); English is used for passages because the checker's questions and verdicts
  are in English, which keeps passage selection accurate with the existing embedding
  model. Explanations are written in French; the link points to the official French text.
  EU legal texts may be reused with attribution (Commission Decision 2011/833/EU).
- Recitals are out of scope (the verdicts cite articles, annexes and chapters).
- Explanations are produced only for complete analyses; one AI call per explanation set.
- The number of explained articles per verdict is bounded (at most 8, in citation order)
  to keep the AI call size and response time reasonable.
