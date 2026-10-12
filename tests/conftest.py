"""Fixtures compartilhadas. Nenhum teste toca em dados reais do usuário:
tudo é gravado em diretórios temporários e a chave da API nunca é lida do ambiente."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from ls_assistant.ai.base import ModelReply, SearchAnswer, ToolDeclaration, Turn
from ls_assistant.config import Settings, load_settings


@pytest.fixture
def sandbox(tmp_path: Path) -> dict[str, Path]:
    """Pastas de dados e de trabalho isoladas."""
    data = tmp_path / "dados"
    docs = tmp_path / "Documentos"
    docs.mkdir()
    return {"data": data, "docs": docs, "root": tmp_path}


@pytest.fixture
def settings(sandbox: dict[str, Path]) -> Settings:
    env = {
        "LS_DATA_DIR": str(sandbox["data"]),
        "LS_ALLOWED_ROOTS": str(sandbox["docs"]),
        "LS_TTS_ENABLED": "false",
        "LS_CONFIRMATION_TIMEOUT_S": "5",
        "LS_TOOL_TIMEOUT_S": "5",
    }
    return load_settings(env, dotenv_path=None)


class ScriptedProvider:
    """Provedor falso: devolve respostas pré-definidas na ordem em que são pedidas."""

    name = "scripted"

    def __init__(self, replies: list[ModelReply | Exception] | None = None, search: SearchAnswer | None = None):
        self.replies = list(replies or [])
        self.search_answer = search or SearchAnswer(text="", sources=[])
        self.calls: list[dict[str, Any]] = []
        self.models = ("fake-model",)

    def generate(self, *, system: str, turns: list[Turn], tools: list[ToolDeclaration]) -> ModelReply:
        self.calls.append({"system": system, "turns": list(turns), "tools": [t.name for t in tools]})
        if not self.replies:
            return ModelReply(text="(sem resposta roteirizada)", tool_calls=[], raw_parts=None, model="fake-model")
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def web_search(self, query: str) -> SearchAnswer:
        return self.search_answer

    def set_models(self, model: str, fallback_models: tuple[str, ...] = ()) -> None:
        self.models = (model, *fallback_models)


@pytest.fixture
def scripted_provider_factory():
    return ScriptedProvider


@pytest.fixture
def ctx(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    """Contexto completo do LS sem IA (sem chave) e sem voz."""
    from ls_assistant.app import build_context

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    context = build_context(settings)
    yield context
    context.shutdown()


@pytest.fixture(autouse=True)
def _no_real_secrets_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Garante que um .env local não afete os testes.
    for var in list(os.environ):
        if var.startswith(("LS_", "GEMINI_")):
            monkeypatch.delenv(var, raising=False)
