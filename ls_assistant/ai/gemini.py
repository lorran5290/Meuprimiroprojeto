"""Provedor Gemini (SDK oficial ``google-genai``).

Comportamento em falhas:
- 429 (cota): uma nova tentativa; depois informa o limite ao usuário.
- 503 / erro de servidor: até 3 tentativas com espera crescente, depois o modelo de fallback.
- 404 (modelo indisponível): passa direto ao próximo modelo configurado.
- 400 / 401 / 403: não repete; informa a causa.
- Rede: repete como erro transitório.

Nenhuma chave é escrita em log ou em mensagens de erro.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ls_assistant.ai.base import ModelReply, SearchAnswer, ToolCall, ToolDeclaration, Turn
from ls_assistant.errors import AIUnavailableError

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_S = (1.0, 2.0)

_MESSAGES = {
    "quota": "A cota de uso da API Gemini foi atingida. Tente de novo mais tarde ou verifique o plano no Google AI Studio.",
    "unavailable": "O serviço Gemini está sobrecarregado no momento. Tentei novamente, mas não obtive resposta.",
    "auth": "A chave da API Gemini foi recusada ou não tem permissão para este modelo. Verifique GEMINI_API_KEY no arquivo .env.",
    "invalid_request": "A API recusou a requisição. Pode ser um modelo ou uma configuração incompatível.",
    "network": "Não consegui conectar ao serviço Gemini. Verifique a internet ou o firewall.",
    "model_unavailable": "O modelo configurado não está disponível para esta chave de API.",
    "unknown": "Ocorreu um erro inesperado ao consultar o Gemini.",
}


def _classify(exc: Exception) -> tuple[str, bool]:
    """Retorna (tipo, pode_repetir) para um erro do SDK."""
    code = getattr(exc, "code", None)
    if code == 429:
        return "quota", True
    if code in (401, 403):
        return "auth", False
    if code == 404:
        return "model_unavailable", False
    if code == 400:
        return "invalid_request", False
    if isinstance(exc, genai_errors.ServerError) or (isinstance(code, int) and code >= 500):
        return "unavailable", True
    return "unknown", False


def _to_part_list(turn: Turn) -> list[types.Part]:
    parts: list[types.Part] = []
    if turn.text:
        parts.append(types.Part(text=turn.text))
    for image in turn.images:
        parts.append(types.Part.from_bytes(data=image.data, mime_type=image.mime_type))
    return parts


def _to_content(turn: Turn) -> types.Content:
    if turn.role == "model":
        if turn.raw_parts is not None:
            return types.Content(role="model", parts=list(turn.raw_parts))
        parts: list[types.Part] = []
        if turn.text:
            parts.append(types.Part(text=turn.text))
        for call in turn.tool_calls:
            parts.append(types.Part(function_call=types.FunctionCall(id=call.call_id, name=call.name, args=call.args)))
        return types.Content(role="model", parts=parts)
    if turn.role == "tool":
        parts = [
            types.Part(
                function_response=types.FunctionResponse(id=r.call_id, name=r.name, response=r.response)
            )
            for r in turn.tool_results
        ]
        return types.Content(role="user", parts=parts)
    return types.Content(role="user", parts=_to_part_list(turn))


def _parse_reply(response: Any, model: str) -> ModelReply:
    candidates = getattr(response, "candidates", None) or []
    if not candidates or candidates[0].content is None:
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(feedback, "block_reason", None) or "sem conteúdo"
        return ModelReply(text=f"Não consegui gerar uma resposta ({reason}).", tool_calls=[], raw_parts=None, model=model)

    parts = list(candidates[0].content.parts or [])
    texts: list[str] = []
    calls: list[ToolCall] = []
    for part in parts:
        if part.function_call is not None:
            fc = part.function_call
            calls.append(ToolCall(name=fc.name or "", args=dict(fc.args or {}), call_id=fc.id))
        elif part.text and not part.thought:
            texts.append(part.text)
    return ModelReply(
        text="".join(texts).strip(),
        tool_calls=calls,
        raw_parts=parts if calls else None,
        model=model,
    )


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        fallback_models: tuple[str, ...] = (),
        timeout_s: float = 60.0,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if client is None:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
            )
        self._client = client
        self._sleep = sleep
        self.models: tuple[str, ...] = ()
        self.set_models(model, fallback_models)
        self.last_model: str | None = None

    @property
    def primary_model(self) -> str:
        return self.models[0]

    def set_models(self, model: str, fallback_models: tuple[str, ...] = ()) -> None:
        """Troca o modelo em tempo de execução (vale a partir da próxima chamada)."""
        self.models = tuple(dict.fromkeys((model, *fallback_models)))

    def generate(self, *, system: str, turns: list[Turn], tools: list[ToolDeclaration]) -> ModelReply:
        contents = [_to_content(t) for t in turns]
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if tools:
            config_kwargs["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ]
        config = types.GenerateContentConfig(**config_kwargs)
        response, model = self._call(contents, config)
        self.last_model = model
        return _parse_reply(response, model)

    def web_search(self, query: str) -> SearchAnswer:
        prompt = (
            "Pesquise na web e responda em português do Brasil, em poucas frases, "
            f"somente com o que as fontes confirmam. Pesquisa: {query}"
        )
        config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        response, model = self._call([prompt], config)
        self.last_model = model
        reply = _parse_reply(response, model)
        sources: list[dict[str, str]] = []
        candidates = getattr(response, "candidates", None) or []
        metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
        for chunk in (getattr(metadata, "grounding_chunks", None) or []):
            web = getattr(chunk, "web", None)
            if web and web.uri:
                sources.append({"titulo": web.title or web.uri, "url": web.uri})
        if not sources:
            return SearchAnswer(
                text="A pesquisa não retornou fontes verificáveis. Não vou apresentar resultados sem fonte.",
                sources=[],
            )
        return SearchAnswer(text=reply.text, sources=sources)

    def _call(self, contents: list[types.Content] | list[str], config: types.GenerateContentConfig) -> tuple[Any, str]:
        last_kind = "unknown"
        for model in self.models:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = self._client.models.generate_content(model=model, contents=contents, config=config)
                    return response, model
                except genai_errors.APIError as exc:
                    kind, retryable = _classify(exc)
                    last_kind = kind
                    log.warning("Gemini %s falhou (%s, tentativa %d): %s", model, kind, attempt + 1, exc.message)
                    if kind == "model_unavailable":
                        break  # tenta o próximo modelo da lista
                    if not retryable:
                        raise AIUnavailableError(_MESSAGES[kind], kind=kind) from exc
                    if kind == "quota" and attempt >= 1:
                        raise AIUnavailableError(_MESSAGES["quota"], kind="quota") from exc
                    if attempt < MAX_ATTEMPTS - 1:
                        self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
                except (OSError, TimeoutError) as exc:  # inclui erros de conexão e timeout
                    last_kind = "network"
                    log.warning("Falha de rede ao consultar Gemini (tentativa %d): %s", attempt + 1, type(exc).__name__)
                    if attempt < MAX_ATTEMPTS - 1:
                        self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
        raise AIUnavailableError(_MESSAGES.get(last_kind, _MESSAGES["unknown"]), kind=last_kind)
