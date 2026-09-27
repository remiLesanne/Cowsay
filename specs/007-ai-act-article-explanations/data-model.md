# Data Model: AI Act Article Explanations

## AI Act corpus — `backend/data/ai_act_en.json` (static, committed)

```json
{
  "source": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689",
  "retrieved": "2026-09-27",
  "articles": {
    "5": {"title": "Prohibited AI practices", "chapter": "II", "section": null,
          "passages": [{"label": "5(1)(f)", "paragraph": "1", "text": "1. The following AI practices shall be prohibited: (f) ..."}]}
  },
  "annexes": {
    "III": {"title": "High-risk AI systems referred to in Article 6(2)",
            "passages": [{"label": "Annex III(4)", "paragraph": "4", "text": "..."}]}
  },
  "chapters": {
    "III": {"title": "HIGH-RISK AI SYSTEMS", "articles": ["6", "..."],
            "sections": {"2": {"title": "Requirements for high-risk AI systems", "articles": ["8", "...", "15"]}}}
  }
}
```

Rules: every article 1–113 and annex I–XIII present; passages in document order; `label`
unique within its article/annex.

## `article_explanations` (new table)

| Field | Type | Rules |
|---|---|---|
| `analysis_id` | UUID, PK, FK → `analyses.id` (cascade delete) | one set per analysis |
| `results_hash` | char(64) | SHA-256 of the verdict text it was generated for (FR-007) |
| `content` | JSONB | the explanation set below |
| `created_at` | timestamptz | |

Regeneration overwrites the row (the previous verdict's explanations are no longer shown
anywhere).

## Explanation set (`content`, also the API response body)

```json
{
  "status": "ready",
  "articles": [
    {"ref": "Article 5", "kind": "article", "number": "5",
     "title": "Prohibited AI practices",
     "url": "https://eur-lex.europa.eu/legal-content/FR/TXT/HTML/?uri=OJ:L_202401689#art_5",
     "passages": [{"label": "5(1)(f)", "text": "..."}],
     "explanation": "…", "why_it_applies": "…", "what_it_implies": "…",
     "available": true}
  ],
  "see_also": [
    {"ref": "Chapter III Section 2", "title": "Requirements for high-risk AI systems",
     "articles": ["8", "9", "…"], "url": "…#cpt_III.sct_2"}
  ]
}
```

`status`: `ready` | `incomplete` (form not complete — nothing generated) |
`no_references` (verdict cites nothing). `available: false` = cited but not in the
corpus (no passages, no explanation).
