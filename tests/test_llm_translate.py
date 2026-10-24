import json
from types import SimpleNamespace

import pytest

from live_translator.llm_translate import (
    ClaudeTranslator, ConversationContext, Glossary, LlmRejected, build_user_message, clean_output,
)
from live_translator.providers import Provider
from live_translator.speech import TranslatorService


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=50, output_tokens=8))


class FakeClient:
    def __init__(self, *responses):
        self.requests = []
        self._responses = list(responses)
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _translator(tmp_path, client, model="claude-haiku-5-5"):
    glossary = Glossary(str(tmp_path / "glossary.json"))
    return ClaudeTranslator(model, glossary, ConversationContext(), key_loader=lambda: "sk-ant-test",
                            client_factory=lambda key: client)


def test_request_carries_context_glossary_and_low_effort(tmp_path):
    (tmp_path / "glossary.json").write_text(json.dumps(
        {"topic": "Elden Ring", "terms": [{"src": "Tarnished", "tgt": "Sönük"}, {"src": "Malenia", "tgt": "Malenia"}]}))
    client = FakeClient(_response("Sönük geri döndü."))
    llm = _translator(tmp_path, client)
    llm.context.add("He fought Malenia.", "Malenia ile savaştı.", "en", "tr")

    assert llm.translate("The Tarnished is back.", "en", "tr") == "Sönük geri döndü."
    req = client.requests[0]
    assert req["model"] == "claude-haiku-5-5"
    assert req["output_config"] == {"effort": "low"}
    assert req["thinking"] == {"type": "disabled"}
    assert "temperature" not in req
    body = req["messages"][0]["content"]
    assert "Tarnished => Sönük" in body and "Malenia => Malenia" in body  # bağlamdaki terim de geliyor
    assert "He fought Malenia. => Malenia ile savaştı." in body
    assert body.endswith("<sentence>The Tarnished is back.</sentence>")


def test_sonnet_request_does_not_disable_thinking(tmp_path):
    client = FakeClient(_response("Merhaba"))
    _translator(tmp_path, client, "claude-sonnet-5-5").translate("Hello", "en", "tr")
    assert "thinking" not in client.requests[0]


def test_refusal_and_odd_output_fall_back_to_classic_chain(tmp_path):
    client = FakeClient(_response("", stop_reason="refusal"), _response("Sure! Here is a long explanation " * 10))
    service = TranslatorService()
    service._classic = (Provider("sahte Google", lambda t, s, g: "klasik"),)
    service.set_llm(_translator(tmp_path, client))

    assert service.translate("A fairly normal sentence.", "en", "tr") == "klasik"
    assert service.translate("Another normal sentence.", "en", "tr") == "klasik"
    # Kısmi sonuçlar Claude'a hiç gitmiyor
    service.translate("partial words", "en", "tr", is_final=False)
    assert len(client.requests) == 2


def test_auth_error_turns_llm_off_for_the_session(tmp_path):
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx2")

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=request), body=None)
    warnings = []
    client = FakeClient(error)
    llm = _translator(tmp_path, client)
    llm._on_disabled = warnings.append
    service = TranslatorService()
    service._classic = (Provider("sahte Google", lambda t, s, g: "klasik"),)
    service.set_llm(llm)

    assert service.translate("First sentence here.", "en", "tr") == "klasik"
    assert service.translate("Second sentence here.", "en", "tr") == "klasik"
    assert len(client.requests) == 1  # ikinci cümlede ağa hiç çıkılmadı
    assert len(warnings) == 1


def test_context_resets_on_language_change_and_long_silence():
    now = [0.0]
    ctx = ConversationContext(clock=lambda: now[0])
    ctx.add("a", "A", "en", "tr")
    assert len(ctx.snapshot("en", "tr")) == 1
    assert ctx.snapshot("de", "tr") == ()
    ctx.add("b", "B", "de", "tr")
    now[0] = 100.0
    assert ctx.snapshot("de", "tr") == ()


def test_clean_output_strips_quotes_and_rejects_runaway_text():
    assert clean_output('"Merhaba dünya"', "Hello world") == "Merhaba dünya"
    with pytest.raises(LlmRejected):
        clean_output("x" * 200, "A normal sentence")
    assert "<context>" not in build_user_message("Hi", (), [], "")
