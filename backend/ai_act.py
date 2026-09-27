"""Guided RAG over the AI Act (specs/007-ai-act-article-explanations).

The checker's verdict decides which articles apply (it cites them); this module only
(1) extracts those references, (2) picks, *inside* each cited article/annex, the
official passages closest to the analysis's answers, and (3) asks the LLM to explain
them in French from those passages only. See research.md for why not a classic RAG.
"""

import asyncio
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np
from fastapi import HTTPException

from code_index import _get_embed_model
from compliance_agent import LLM_API_URL, LLM_MODEL, _get_http_client

logger = logging.getLogger(__name__)

CORPUS_PATH = Path(__file__).parent / "data" / "ai_act_en.json"
OFFICIAL_FR_URL = "https://eur-lex.europa.eu/legal-content/FR/TXT/HTML/?uri=OJ:L_202401689"
MAX_EXPLAINED_REFS = 8
PASSAGES_PER_REF = 3
MAX_PASSAGE_CHARS_IN_PROMPT = 1500
# Part of the cache key (history.py): bump it when the prompt changes so explanations
# stored with an older prompt are regenerated instead of served forever.
EXPLANATION_VERSION = 2

_CHAPTER_RE = re.compile(r"\bChapter\s+([IVXL]+)(?:\s*,?\s*Section\s+(\d+))?")
_ANNEX_RE = re.compile(r"\bAnnex(?:es)?\s+([IVXL]+(?:\s*(?:,|and|or)\s*[IVXL]+)*)\b")
# "Article 5", "Article 6(2)", "Article 49 point 2", "Article 50, point 3",
# "Articles 16 and 17", "Articles 8 to 15"
_ARTICLE_ITEM = r"\d+(?:\s*\(\d+\))?(?:,?\s+(?:point|paragraph)\s+\d+[a-z]?)?"
_ARTICLE_RE = re.compile(rf"\bArticles?\s+({_ARTICLE_ITEM}(?:\s*(?:,|and|or|to)\s*{_ARTICLE_ITEM})*)")


@lru_cache(maxsize=1)
def load_corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _article_items(group: str) -> list[tuple[str, str | None]]:
    """"6 point 2a" -> [("6", "2")]; "8 to 11" -> 8..11; "16 and 17" -> [16, 17]."""
    items: list[tuple[str, str | None]] = []
    group = re.sub(r",\s*(point|paragraph)\b", r" \1", group)  # "50, point 3" -> "50 point 3"
    tokens = re.split(r"\s*(,|and|or|to)\s*", group)
    previous_number, pending_range = None, False
    for token in tokens:
        if token in (",", "and", "or"):
            continue
        if token == "to":
            pending_range = True
            continue
        match = re.match(r"(\d+)(?:\s*\((\d+)\))?(?:\s+(?:point|paragraph)\s+(\d+))?", token)
        if not match:
            continue
        number, paragraph = match.group(1), match.group(2) or match.group(3)
        if pending_range and previous_number is not None:
            items.extend((str(n), None) for n in range(int(previous_number) + 1, int(number)))
        items.append((number, paragraph))
        previous_number, pending_range = number, False
    return items


def extract_references(results_text: str) -> list[dict]:
    """Every article/annex/chapter reference in the verdict, in citation order, once.

    Articles and annexes are capped at MAX_EXPLAINED_REFS (spec Assumptions);
    chapter/section references become "see also" entries and don't count.
    """
    text = _one_line(results_text)
    found: list[tuple[int, dict]] = []
    for match in _CHAPTER_RE.finditer(text):
        found.append((match.start(), {"kind": "chapter", "number": match.group(1), "section": match.group(2)}))
    for match in _ANNEX_RE.finditer(text):
        for roman in re.findall(r"[IVXL]+", match.group(1)):
            found.append((match.start(), {"kind": "annex", "number": roman}))
    for match in _ARTICLE_RE.finditer(text):
        for number, paragraph in _article_items(match.group(1)):
            found.append((match.start(), {"kind": "article", "number": number, "paragraph": paragraph}))
    found.sort(key=lambda item: item[0])

    refs: list[dict] = []
    by_key: dict[tuple, dict] = {}
    explained = 0
    for _, ref in found:
        key = (ref["kind"], ref["number"], ref.get("section"))
        if key in by_key:
            if ref.get("paragraph"):
                by_key[key]["paragraphs"].add(ref["paragraph"])
            continue
        if ref["kind"] != "chapter":
            if explained >= MAX_EXPLAINED_REFS:
                continue
            explained += 1
        entry = {**ref, "paragraphs": {ref["paragraph"]} if ref.get("paragraph") else set()}
        entry.pop("paragraph", None)
        by_key[key] = entry
        refs.append(entry)
    return refs


def _ref_key(text: str) -> tuple[str, str] | None:
    """("article", "5") from "Article 5", "Article 5(1)(f)", "Article 5 — Prohibited…";
    the LLM doesn't always echo a reference exactly as it was listed."""
    match = re.search(r"\b(Article|Annex)\s+(\d+|[IVXL]+)", text or "", re.IGNORECASE)
    return (match.group(1).lower(), match.group(2).upper()) if match else None


def _generated_by_ref(answer: dict) -> dict[tuple[str, str], dict]:
    items = answer.get("articles")
    if not isinstance(items, list):  # e.g. {"Article 5": {...}} instead of the asked shape
        items = [{**value, "ref": key} for key, value in answer.items() if isinstance(value, dict)]
    by_ref: dict[tuple[str, str], dict] = {}
    for item in items:
        key = _ref_key(str(item.get("ref", ""))) if isinstance(item, dict) else None
        if key:
            by_ref.setdefault(key, item)
    return by_ref


def _ref_label(ref: dict) -> str:
    if ref["kind"] == "article":
        return f"Article {ref['number']}"
    if ref["kind"] == "annex":
        return f"Annex {ref['number']}"
    return f"Chapter {ref['number']}" + (f" Section {ref['section']}" if ref.get("section") else "")


def _source_entry(ref: dict) -> dict | None:
    corpus = load_corpus()
    group = corpus["articles"] if ref["kind"] == "article" else corpus["annexes"]
    return group.get(ref["number"])


@lru_cache(maxsize=256)
def _passage_embeddings(kind: str, number: str) -> np.ndarray:
    # The corpus is static, so each article's passages are embedded once per process.
    entry = _source_entry({"kind": kind, "number": number})
    vectors = _get_embed_model().get_text_embedding_batch([p["text"] for p in entry["passages"]])
    return _normalize(np.array(vectors, dtype=np.float32))


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_queries(results_text: str, question_details: list[dict]) -> list[str]:
    """One query per answered question, answer first: the embedding model only reads
    ~256 tokens, so one long concatenated query would silently drop later answers."""
    queries = [_one_line(results_text)]
    for detail in question_details or []:
        answer = detail.get("answer")
        answer_text = ", ".join(answer) if isinstance(answer, list) else (answer or "")
        if answer_text:
            queries.append(f"{answer_text}. {_one_line(detail.get('question', ''))}")
    return [query for query in queries if query]


def select_passages(ref: dict, query_vectors: np.ndarray) -> list[dict]:
    """Top passages of ONE article/annex (never outside it — that is the "guided" part),
    scored by their best similarity to any query, plus any explicitly cited paragraph.
    Returned in document order so excerpts read naturally."""
    passages = _source_entry(ref)["passages"]
    if len(passages) <= PASSAGES_PER_REF:
        return passages
    scores = (_passage_embeddings(ref["kind"], ref["number"]) @ query_vectors.T).max(axis=1)
    chosen = set(np.argsort(-scores)[:PASSAGES_PER_REF].tolist())
    chosen |= {i for i, p in enumerate(passages) if p.get("paragraph") in ref["paragraphs"]}
    return [passages[i] for i in sorted(chosen)]


def _official_url(ref: dict) -> str:
    if ref["kind"] == "article":
        anchor = f"art_{ref['number']}"
    elif ref["kind"] == "annex":
        anchor = f"anx_{ref['number']}"
    else:
        anchor = f"cpt_{ref['number']}" + (f".sct_{ref['section']}" if ref.get("section") else "")
    return f"{OFFICIAL_FR_URL}#{anchor}"


def _see_also_entry(ref: dict) -> dict:
    chapter = load_corpus()["chapters"].get(ref["number"], {})
    source = chapter["sections"].get(ref["section"], {}) if ref.get("section") and chapter else chapter
    title = source.get("title_fr") or source.get("title", "")
    return {
        "ref": _ref_label(ref),
        # Chapter titles are upper case in the OJ ("SYSTÈMES D’IA À HAUT RISQUE").
        "title": re.sub(r"\bia\b", "IA", title.capitalize()) if title.isupper() else title,
        "articles": source.get("articles", []),
        "url": _official_url(ref),
    }


def _prompt(results_text: str, question_details: list[dict], selections: list[tuple[dict, list[dict]]]) -> str:
    qa_lines = []
    for detail in question_details or []:
        answer = detail.get("answer")
        answer_text = ", ".join(answer) if isinstance(answer, list) else (answer or "")
        source = "user" if detail.get("source") == "human" else "AI, from the code"
        question = _one_line(detail.get("question", ""))
        qa_lines.append(f"- Q: {question}\n  A ({source}): {answer_text or '(none)'}")
    blocks = []
    for ref, passages in selections:
        entry = _source_entry(ref)
        excerpts = "\n".join(
            f"  [{p['label']}] {p['text'][:MAX_PASSAGE_CHARS_IN_PROMPT]}" for p in passages
        )
        blocks.append(f"{_ref_label(ref)} — {entry['title']}\n{excerpts}")

    refs_list = ", ".join(f'"{_ref_label(ref)}"' for ref, _ in selections)
    return (
        "You help a development team understand the result of the official EU AI Act "
        "Compliance Checker for their AI system. The checker's verdict is authoritative: do "
        "not contradict it and do not bring in any article that is not listed below.\n\n"
        f"Checker verdict:\n{results_text}\n\n"
        f"Questionnaire answers:\n{chr(10).join(qa_lines) or '(none)'}\n\n"
        f"Official excerpts of the articles the verdict cites (English, Regulation (EU) 2024/1689):\n\n"
        f"{chr(10).join(blocks)}\n\n"
        "Strict rules: every statement must be supported by the excerpts above or by a "
        "questionnaire answer. Never draw a conclusion from the system's name or file names. "
        "Do not add obligations, penalties or facts that the excerpts do not contain.\n\n"
        "For EACH of these references: " + refs_list + ", write in French:\n"
        "- title_fr: the article's title in French\n"
        "- explanation: what the excerpts shown for it say, in plain language (2-3 sentences)\n"
        "- why_it_applies: go through the excerpts shown for this reference; for each one that "
        "matches an answer, cite its label (e.g. 5(1)(f)) and the answer that triggers it; if an "
        "excerpt does not apply to this system, say so in a few words; if the answers do not "
        "settle which point applies, say so explicitly instead of guessing\n"
        "- what_it_implies: the concrete consequence for the team, as stated by the excerpts "
        "(1-3 sentences)\n\n"
        'Reply with ONLY a JSON object: {"articles": [{"ref": "<reference exactly as listed>", '
        '"title_fr": "...", "explanation": "...", "why_it_applies": "...", "what_it_implies": "..."}]}'
    )


async def _ask_llm(prompt: str) -> dict:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY n’est pas configurée sur le serveur")
    try:
        response = await _get_http_client().post(
            LLM_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
        )
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Le modèle a mis trop de temps à répondre") from error
    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail=f"Impossible de contacter le modèle ({error})") from error
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"L’appel au modèle a échoué ({response.status_code})")
    try:
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Réponse du modèle illisible") from error


def _select_all(refs: list[dict], results_text: str, question_details: list[dict]) -> list[tuple[dict, list[dict]]]:
    if not refs:
        return []
    vectors = _get_embed_model().get_text_embedding_batch(build_queries(results_text, question_details))
    query_vectors = _normalize(np.array(vectors, dtype=np.float32))
    return [(ref, select_passages(ref, query_vectors)) for ref in refs]


async def explain(results_text: str, question_details: list[dict]) -> dict:
    """The explanation set for one complete verdict (data-model.md). Raises
    HTTPException on LLM failure so nothing wrong gets cached."""
    refs = extract_references(results_text)
    explained_refs = [ref for ref in refs if ref["kind"] != "chapter"]
    see_also = [_see_also_entry(ref) for ref in refs if ref["kind"] == "chapter"]
    if not refs:
        return {"status": "no_references", "articles": [], "see_also": []}

    available = [ref for ref in explained_refs if _source_entry(ref)]
    # Embedding is CPU-bound: off the event loop, like code_index in compliance_agent.
    selections = await asyncio.to_thread(_select_all, available, results_text, question_details)

    by_ref: dict[tuple[str, str], dict] = {}
    if selections:
        logger.info("Generating AI Act explanations for %s", [_ref_label(ref) for ref, _ in selections])
        answer = await _ask_llm(_prompt(results_text, question_details, selections))
        by_ref = _generated_by_ref(answer)

    selected = {id(ref): passages for ref, passages in selections}
    articles = []
    for ref in explained_refs:
        entry = _source_entry(ref)
        generated = by_ref.get(_ref_key(_ref_label(ref)), {})
        if entry is not None and not generated.get("explanation"):
            logger.warning("No explanation generated for %s", _ref_label(ref))
        articles.append({
            "ref": _ref_label(ref),
            "kind": ref["kind"],
            "number": ref["number"],
            # Official French title from the corpus; the LLM's translation only as a fallback.
            "title": (entry or {}).get("title_fr") or generated.get("title_fr") or (entry or {}).get("title", ""),
            "url": _official_url(ref),
            "available": entry is not None,
            "passages": [{"label": p["label"], "text": p["text"]} for p in selected.get(id(ref), [])],
            "explanation": generated.get("explanation", ""),
            "why_it_applies": generated.get("why_it_applies", ""),
            "what_it_implies": generated.get("what_it_implies", ""),
        })
    return {"status": "ready", "articles": articles, "see_also": see_also}
