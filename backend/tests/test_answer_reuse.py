import asyncio

from compliance_agent import answer_field

RADIO_FIELD = {
    "id": "f1",
    "type": "radio",
    "question": "Entity type",
    "options": [{"id": "o1", "value": "Provider"}, {"id": "o2", "value": "Deployer"}],
}


class FakeLlm:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.answer


def _answer(field, human, cache, llm):
    return asyncio.run(answer_field(field, human, cache, llm))


def test_new_ai_answer_is_cached_for_later_rounds():
    cache = {}
    llm = FakeLlm({"selected": ["Provider"], "confidence": "high", "reasoning": "r"})
    answer, source = _answer(RADIO_FIELD, {}, cache, llm)
    assert (answer["selected"], source, llm.calls) == (["Provider"], "ai", 1)
    assert cache["f1"] is answer


def test_cached_ai_answer_is_reused_without_calling_the_llm():
    cache = {"f1": {"selected": ["Deployer"], "confidence": "high", "reasoning": "r"}}
    llm = FakeLlm(None)
    answer, source = _answer(RADIO_FIELD, None, cache, llm)
    assert (answer["selected"], source, llm.calls) == (["Deployer"], "ai", 0)


def test_human_answer_wins_over_a_cached_ai_answer():
    cache = {"f1": {"selected": ["Deployer"], "confidence": "low", "reasoning": "r"}}
    llm = FakeLlm(None)
    answer, source = _answer(RADIO_FIELD, {"f1": "Provider"}, cache, llm)
    assert (answer["selected"], source, llm.calls) == (["Provider"], "human", 0)


def test_cached_answer_whose_option_disappeared_is_escalated_not_clicked():
    # An earlier answer changed which options the form shows: "Importer" is gone.
    cache = {"f1": {"selected": ["Importer"], "confidence": "high", "reasoning": "r"}}
    answer, _ = _answer(RADIO_FIELD, None, cache, FakeLlm(None))
    assert answer["selected"] == []
    assert answer["confidence"] == "low"


def test_without_a_cache_every_round_asks_the_llm():
    llm = FakeLlm({"selected": ["Provider"], "confidence": "high"})
    _answer(RADIO_FIELD, None, None, llm)
    _answer(RADIO_FIELD, None, None, llm)
    assert llm.calls == 2
