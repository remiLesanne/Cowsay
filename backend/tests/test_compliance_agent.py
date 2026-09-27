import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

import compliance_agent
from compliance_agent import normalize_llm_answer

RADIO_FIELD = {
    "id": "f1",
    "type": "radio",
    "question": "Entity type",
    "options": [{"id": "o1", "value": "Provider"}, {"id": "o2", "value": "Deployer"}],
}
CHECKBOX_FIELD = {**RADIO_FIELD, "type": "checkbox"}
TEXT_FIELD = {"id": "f2", "type": "text", "question": "System name", "inputId": "i2"}


def test_bare_string_selection_becomes_a_list():
    answer = normalize_llm_answer(RADIO_FIELD, {"selected": "provider", "confidence": "High"})
    assert answer["selected"] == ["Provider"]
    assert answer["confidence"] == "high"


def test_options_not_in_the_form_are_dropped_and_sent_to_the_human():
    answer = normalize_llm_answer(CHECKBOX_FIELD, {"selected": ["Importer"], "confidence": "high"})
    assert answer["selected"] == []
    assert answer["confidence"] == "low"


def test_several_answers_to_a_radio_question_are_not_guessed():
    answer = normalize_llm_answer(RADIO_FIELD, {"selected": ["Provider", "Deployer"], "confidence": "high"})
    assert answer["selected"] == []
    assert answer["confidence"] == "low"


def test_checkbox_keeps_every_valid_option_once():
    answer = normalize_llm_answer(
        CHECKBOX_FIELD, {"selected": ["Deployer", "provider", "Provider", None], "confidence": "medium"}
    )
    assert answer["selected"] == ["Deployer", "Provider"]


def test_malformed_payloads_do_not_crash():
    assert normalize_llm_answer(RADIO_FIELD, None)["selected"] == []
    assert normalize_llm_answer(RADIO_FIELD, {"selected": None})["confidence"] == "low"
    assert normalize_llm_answer(TEXT_FIELD, {"text": 42})["text"] == ""


def _llm_reply(content: dict) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})


def _ask_with_transport(monkeypatch, handler):
    monkeypatch.setattr(
        compliance_agent, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(compliance_agent, "LLM_RETRY_BASE_DELAY_S", 0)
    monkeypatch.setattr(compliance_agent, "_pacer", compliance_agent.LlmPacer())
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    return asyncio.run(compliance_agent._ask_llm_for_answer(RADIO_FIELD, "", ""))


def test_requests_are_deterministic(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return _llm_reply({"selected": ["Provider"], "confidence": "high"})

    _ask_with_transport(monkeypatch, handler)
    assert bodies[0]["temperature"] == 0


def test_transient_llm_errors_are_retried(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429)
        return _llm_reply({"selected": ["Provider"], "confidence": "high", "reasoning": "r"})

    answer = _ask_with_transport(monkeypatch, handler)
    assert answer["selected"] == ["Provider"]
    assert len(calls) == 3


def test_client_errors_are_not_retried(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    with pytest.raises(HTTPException) as error:
        _ask_with_transport(monkeypatch, handler)
    assert error.value.status_code == 502
    assert len(calls) == 1


def test_llm_gives_up_after_max_attempts(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(HTTPException):
        _ask_with_transport(monkeypatch, handler)
    assert len(calls) == compliance_agent.LLM_MAX_ATTEMPTS
