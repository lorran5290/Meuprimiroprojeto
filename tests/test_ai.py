"""Provedor Gemini (erros, retentativas, fallback de modelo, partes preservadas) e orquestrador do LS."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from ls_assistant.ai.assistant import Assistant
from ls_assistant.ai.base import ImageInput, ModelReply, ToolCall, ToolResult, Turn
from ls_assistant.ai.conversation import Conversation
from ls_assistant.ai.gemini import GeminiProvider, _parse_reply, _to_content
from ls_assistant.errors import AIUnavailableError
from ls_assistant.security import CancelToken


# Cliente falso do SDK ---------------------------------------------------------
class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models_called: list[str] = []

    def generate_content(self, *, model, contents, config):
        self.models_called.append(model)
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def fake_client(outcomes):
    models = FakeModels(outcomes)
    return SimpleNamespace(models=models), models


def _text_response(text: str):
    part = types.Part(text=text)
    return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]))])


def _client_error(code: int, status: str = "X"):
    return genai_errors.ClientError(code, {"error": {"code": code, "message": f"erro {code}", "status": status}})


def _server_error(code: int = 503):
    return genai_errors.ServerError(code, {"error": {"code": code, "message": "alta demanda", "status": "UNAVAILABLE"}})


def _no_sleep(_seconds: float) -> None:
    return None


def test_text_reply_parsed_and_thought_parts_ignored():
    thought = types.Part(text="raciocínio interno", thought=True)
    answer = types.Part(text="Olá!")
    response = SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[thought, answer]))])
    reply = _parse_reply(response, "m")
    assert reply.text == "Olá!" and reply.tool_calls == [] and reply.raw_parts is None


def test_function_call_is_parsed_and_raw_parts_kept_for_signatures():
    call = types.Part(function_call=types.FunctionCall(id="c1", name="listar_pasta", args={"caminho": "Documentos"}),
                      thought_signature=b"assinatura")
    response = SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[call]))])
    reply = _parse_reply(response, "m")
    assert reply.tool_calls == [ToolCall(name="listar_pasta", args={"caminho": "Documentos"}, call_id="c1")]
    # As partes originais voltam ao modelo sem alteração (inclui a assinatura).
    rebuilt = _to_content(Turn(role="model", raw_parts=reply.raw_parts))
    assert rebuilt.parts[0].thought_signature == b"assinatura"


def test_tool_results_are_sent_as_function_responses():
    content = _to_content(Turn(role="tool", tool_results=[ToolResult(name="x", response={"status": "ok"}, call_id="c1")]))
    fr = content.parts[0].function_response
    assert fr.name == "x" and fr.response == {"status": "ok"} and fr.id == "c1"


def test_user_images_are_sent_as_inline_data():
    content = _to_content(Turn(role="user", text="veja", images=[ImageInput(data=b"\x89PNG", mime_type="image/png")]))
    assert content.parts[1].inline_data.mime_type == "image/png"


def test_rate_limit_retries_once_then_reports_quota():
    client, models = fake_client([_client_error(429, "RESOURCE_EXHAUSTED"), _client_error(429, "RESOURCE_EXHAUSTED")])
    provider = GeminiProvider("k", "gemini-3.5-flash", client=client, sleep=_no_sleep)
    with pytest.raises(AIUnavailableError) as info:
        provider.generate(system="s", turns=[Turn(role="user", text="oi")], tools=[])
    assert info.value.kind == "quota"
    assert len(models.models_called) == 2


def test_overload_retries_then_uses_fallback_model():
    outcomes = [_server_error(), _server_error(), _server_error(), _text_response("respondi pelo modelo de reserva")]
    client, models = fake_client(outcomes)
    provider = GeminiProvider("k", "gemini-3.8-flash", fallback_models=("gemini-3.5-flash",), client=client, sleep=_no_sleep)
    reply = provider.generate(system="s", turns=[Turn(role="user", text="oi")], tools=[])
    assert reply.text == "respondi pelo modelo de reserva"
    assert models.models_called == ["gemini-3.8-flash"] * 3 + ["gemini-3.5-flash"]


def test_model_not_found_skips_to_next_model_without_retry():
    client, models = fake_client([_client_error(404, "NOT_FOUND"), _text_response("ok")])
    provider = GeminiProvider("k", "gemini-antigo", fallback_models=("gemini-3.5-flash",), client=client, sleep=_no_sleep)
    provider.generate(system="s", turns=[Turn(role="user", text="oi")], tools=[])
    assert models.models_called == ["gemini-antigo", "gemini-3.5-flash"]


def test_invalid_key_is_reported_without_retry():
    client, models = fake_client([_client_error(403, "PERMISSION_DENIED")])
    provider = GeminiProvider("k", "gemini-3.5-flash", client=client, sleep=_no_sleep)
    with pytest.raises(AIUnavailableError) as info:
        provider.generate(system="s", turns=[Turn(role="user", text="oi")], tools=[])
    assert info.value.kind == "auth"
    assert len(models.models_called) == 1
    assert "GEMINI_API_KEY" in str(info.value)


def test_network_failure_is_retried_then_reported():
    client, models = fake_client([ConnectionError("sem rede"), ConnectionError("sem rede"), ConnectionError("sem rede")])
    provider = GeminiProvider("k", "gemini-3.5-flash", client=client, sleep=_no_sleep)
    with pytest.raises(AIUnavailableError) as info:
        provider.generate(system="s", turns=[Turn(role="user", text="oi")], tools=[])
    assert info.value.kind == "network"
    assert len(models.models_called) == 3


def test_set_models_takes_effect_on_next_call():
    client, models = fake_client([_text_response("a"), _text_response("b")])
    provider = GeminiProvider("k", "gemini-3.5-flash", client=client, sleep=_no_sleep)
    provider.generate(system="s", turns=[], tools=[])
    provider.set_models("gemini-3.8-flash", ())
    provider.generate(system="s", turns=[], tools=[])
    assert models.models_called == ["gemini-3.5-flash", "gemini-3.8-flash"]


# Orquestrador ----------------------------------------------------------------------
class SequenceProvider:
    """Respostas roteirizadas do modelo (texto ou chamadas de ferramenta)."""

    name = "seq"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen_tool_results: list[list] = []

    def generate(self, *, system, turns, tools):
        for turn in turns:
            if turn.role == "tool":
                self.seen_tool_results.append(turn.tool_results)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def web_search(self, query):  # pragma: no cover - não usado aqui
        raise NotImplementedError


def _assistant(ctx, provider, *, keep_history=True):
    return Assistant(provider=provider, executor=ctx.executor, memory=ctx.memory, conversation=Conversation(),
                     events=ctx.events, keep_history=keep_history)


def test_plain_answer_is_returned_and_logged(ctx):
    provider = SequenceProvider([ModelReply(text="Tudo certo.", tool_calls=[], raw_parts=None, model="m")])
    reply = _assistant(ctx, provider).respond("como vai?")
    assert reply.text == "Tudo certo." and reply.mode == "ia"
    assert [m["role"] for m in ctx.memory.recent_messages()] == ["usuario", "ls"]


def test_tool_call_result_goes_back_to_model(ctx, sandbox):
    (sandbox["docs"] / "a.txt").write_text("x")
    provider = SequenceProvider([
        ModelReply(text="", tool_calls=[ToolCall(name="listar_pasta", args={}, call_id="1")], raw_parts=[], model="m"),
        ModelReply(text="Há 1 arquivo: a.txt.", tool_calls=[], raw_parts=None, model="m"),
    ])
    reply = _assistant(ctx, provider).respond("liste meus documentos")
    assert reply.text == "Há 1 arquivo: a.txt."
    result = provider.seen_tool_results[0][0]
    assert result.name == "listar_pasta" and result.response["status"] == "ok"
    assert reply.actions and reply.actions[0]["tool"] == "listar_pasta"


def test_model_gets_denial_and_must_not_claim_success(ctx):
    provider = SequenceProvider([
        ModelReply(text="", tool_calls=[ToolCall(name="esquecer_memoria", args={"memoria_id": 1}, call_id="1")], raw_parts=[], model="m"),
        ModelReply(text="Não apaguei a memória porque não houve aprovação.", tool_calls=[], raw_parts=None, model="m"),
    ])
    # Sem broker respondendo, o prazo de confirmação expira (ver conftest: 5 s).
    reply = _assistant(ctx, provider).respond("apague a memória 1")
    assert "não" in reply.text.lower()
    assert provider.seen_tool_results[0][0].response["status"] == "denied"


def test_unavailable_ai_falls_back_to_local_tools(ctx):
    provider = SequenceProvider([AIUnavailableError("sem serviço", kind="network")])
    reply = _assistant(ctx, provider).respond("como está o estado do computador?")
    assert reply.mode == "local"
    assert "A IA não está disponível agora" in reply.text
    assert reply.actions and reply.actions[0]["tool"] == "status_do_sistema"


def test_no_provider_reports_how_to_fix(ctx):
    reply = Assistant(provider=None, executor=ctx.executor, memory=ctx.memory, conversation=Conversation(),
                      events=ctx.events).respond("oi")
    assert reply.mode == "local" and "GEMINI_API_KEY" in reply.text


def test_cancellation_stops_the_loop(ctx):
    token = CancelToken()
    token.cancel("teste")
    provider = SequenceProvider([ModelReply(text="não deveria chegar", tool_calls=[], raw_parts=None, model="m")])
    reply = _assistant(ctx, provider).respond("algo longo", cancel=token)
    assert reply.mode == "cancelado"
    assert provider.replies  # o modelo nem foi chamado


def test_step_limit_prevents_infinite_tool_loops(ctx):
    looping = ModelReply(text="", tool_calls=[ToolCall(name="status_do_sistema", args={}, call_id="x")], raw_parts=[], model="m")
    provider = SequenceProvider([looping] * 10)
    assistant = Assistant(provider=provider, executor=ctx.executor, memory=ctx.memory, conversation=Conversation(),
                          events=ctx.events, max_steps=3)
    reply = assistant.respond("loop")
    assert reply.mode == "limite"


def test_image_from_tool_is_attached_for_next_turn(ctx, monkeypatch):
    from ls_assistant.tools import builtin

    monkeypatch.setattr(builtin, "capture_screen_png", lambda: b"\x89PNG-fake")
    provider = SequenceProvider([
        ModelReply(text="", tool_calls=[ToolCall(name="capturar_tela", args={}, call_id="1")], raw_parts=[], model="m"),
        ModelReply(text="Vejo uma janela de erro.", tool_calls=[], raw_parts=None, model="m"),
    ])
    # Captura exige aprovação: aprova automaticamente nesta chamada de teste.
    import threading
    import time as _t

    def approve():
        for _ in range(200):
            pending = ctx.broker.pending()
            if pending:
                ctx.broker.resolve(pending[0]["id"], True)
                return
            _t.sleep(0.02)

    threading.Thread(target=approve, daemon=True).start()
    reply = _assistant(ctx, provider).respond("veja minha tela")
    assert reply.text == "Vejo uma janela de erro."
    assert reply.actions[0]["status"] == "ok"


def test_memory_context_includes_only_non_sensitive_items(ctx):
    ctx.memory.add("Dado secreto de teste.", category="projetos", key="Projeto X", sensitive=True)
    ctx.memory.add("Projeto X é um app de teste.", category="projetos", key="Projeto X")
    seen = {}

    class Capture(SequenceProvider):
        def generate(self, *, system, turns, tools):
            seen["system"] = system
            return super().generate(system=system, turns=turns, tools=tools)

    provider = Capture([ModelReply(text="ok", tool_calls=[], raw_parts=None, model="m")])
    _assistant(ctx, provider).respond("fale sobre o Projeto X")
    assert "app de teste" in seen["system"]
    assert "Dado secreto" not in seen["system"]


def test_conversation_trim_keeps_pairs_intact():
    conv = Conversation(max_turns=4)
    conv.add(Turn(role="user", text="1"))
    conv.add(Turn(role="model", text="a"))
    conv.add(Turn(role="user", text="2"))
    conv.add(Turn(role="model", text="b"))
    conv.add(Turn(role="user", text="3"))
    turns = conv.turns()
    assert turns[0].role == "user"
    assert len(turns) <= 4
