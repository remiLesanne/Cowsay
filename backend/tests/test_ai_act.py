import asyncio
import json

import httpx

import ai_act
import compliance_agent


def _refs(text):
    return [(ref["kind"], ref["number"], ref.get("section")) for ref in ai_act.extract_references(text)]


def test_references_are_extracted_in_citation_order_once():
    text = (
        "Your system is high-risk under Article 6(2) and Annex III. Obligations: "
        "Articles 8 to 11 and Article 6 again; see Chapter III, Section 2."
    )
    assert _refs(text) == [
        ("article", "6", None),
        ("annex", "III", None),
        ("article", "8", None),
        ("article", "9", None),
        ("article", "10", None),
        ("article", "11", None),
        ("chapter", "III", "2"),
    ]


def test_cited_paragraphs_are_kept():
    refs = ai_act.extract_references("See Article 50, point 3 and Article 50(1).")
    assert refs == [{"kind": "article", "number": "50", "paragraphs": {"3", "1"}}]


def test_explained_references_are_capped_but_chapters_are_not():
    many = " ".join(f"Article {n}." for n in range(1, 20)) + " Chapter IV."
    refs = ai_act.extract_references(many)
    assert sum(1 for ref in refs if ref["kind"] == "article") == ai_act.MAX_EXPLAINED_REFS
    assert refs[-1]["kind"] == "chapter"


def test_explanations_go_through_the_shared_paced_llm_call(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"articles": []}'}}]})

    monkeypatch.setattr(
        compliance_agent, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(compliance_agent, "_pacer", compliance_agent.LlmPacer())
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    assert asyncio.run(ai_act._ask_llm("prompt")) == {"articles": []}
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["temperature"] == 0.2  # its own setting overrides the default 0
    assert len(compliance_agent._pacer._calls) == 1  # counted against the shared quota
