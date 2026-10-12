"""Testes contra a API real do Gemini.

Rodam só com GEMINI_API_KEY definida (ex.: no .env ou no ambiente). Sem a chave, são pulados.
Eles gastam cota real: rode com ``pytest -m live``.
"""

from __future__ import annotations

import os

import pytest

from ls_assistant.ai.base import ToolDeclaration, Turn
from ls_assistant.ai.gemini import GeminiProvider
from ls_assistant.errors import AIUnavailableError

FAKE_NEW_KEY = "AQ" + "." + "chave-invalida-de-teste" + "-" + "123456"  # formato apenas

pytestmark = pytest.mark.live

KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
requires_key = pytest.mark.skipif(not KEY, reason="GEMINI_API_KEY não definida")


def _or_skip_on_quota(call):
    """Cota esgotada é condição externa: o teste é pulado com o motivo, não reprovado."""
    try:
        return call()
    except AIUnavailableError as exc:
        if exc.kind == "quota":
            pytest.skip("cota da API esgotada nesta chave (429); teste não avaliado agora")
        raise


@requires_key
def test_portuguese_conversation_returns_coherent_answer():
    provider = GeminiProvider(KEY, MODEL, timeout_s=60)
    reply = _or_skip_on_quota(lambda: provider.generate(
        system="Você é o LS, assistente em português do Brasil. Seja breve.",
        turns=[Turn(role="user", text="Responda em uma frase: qual é a capital do Brasil?")],
        tools=[],
    ))
    assert reply.text
    assert "Brasília" in reply.text or "Brasilia" in reply.text


@requires_key
def test_function_calling_produces_structured_call():
    provider = GeminiProvider(KEY, MODEL, timeout_s=60)
    decl = ToolDeclaration(
        name="abrir_pasta",
        description="Abre uma pasta do computador do usuário.",
        parameters={"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]},
    )
    reply = _or_skip_on_quota(lambda: provider.generate(
        system="Você é o LS. Use as ferramentas quando o usuário pedir uma ação no computador.",
        turns=[Turn(role="user", text="Abra a pasta Documentos, por favor.")],
        tools=[decl],
    ))
    assert reply.tool_calls and reply.tool_calls[0].name == "abrir_pasta"
    assert "Documentos" in str(reply.tool_calls[0].args.get("nome", ""))


@requires_key
def test_web_search_only_returns_sources_it_received():
    provider = GeminiProvider(KEY, MODEL, timeout_s=60)
    try:
        answer = provider.web_search("Qual é a versão estável mais recente do Python?")
    except AIUnavailableError as exc:
        pytest.skip(f"Pesquisa com fontes indisponível nesta chave/cota: {exc.kind}")
    if not answer.sources:
        assert "não" in answer.text.lower()  # sem fonte, o LS admite em vez de inventar
    else:
        assert all(s["url"].startswith("http") for s in answer.sources)


def test_invalid_key_is_reported_clearly_without_leaking_key():
    provider = GeminiProvider(FAKE_NEW_KEY, MODEL, timeout_s=20, sleep=lambda s: None)
    with pytest.raises(AIUnavailableError) as info:
        provider.generate(system="s", turns=[Turn(role="user", text="oi")], tools=[])
    assert info.value.kind in {"auth", "network", "unknown", "invalid_request"}
    assert "chave-invalida" not in str(info.value)
