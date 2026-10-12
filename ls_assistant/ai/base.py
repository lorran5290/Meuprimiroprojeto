"""Contrato neutro entre o LS e qualquer provedor de IA.

O restante do programa conversa só com estes tipos. Trocar o Gemini por outro
modelo significa implementar ``AIProvider`` em um novo arquivo, sem mudar o
orquestrador, as ferramentas ou a interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["user", "model", "tool"]


@dataclass(frozen=True)
class ImageInput:
    data: bytes
    mime_type: str = "image/png"


@dataclass(frozen=True)
class ToolDeclaration:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str | None = None


@dataclass
class ToolResult:
    name: str
    response: dict[str, Any]
    call_id: str | None = None


@dataclass
class Turn:
    """Uma entrada da conversa enviada ao modelo."""

    role: Role
    text: str = ""
    images: list[ImageInput] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    # Partes exatas devolvidas pelo provedor. Necessárias para manter assinaturas
    # internas de chamadas de função; são opacas para o resto do programa.
    raw_parts: Any = None


@dataclass
class ModelReply:
    text: str
    tool_calls: list[ToolCall]
    raw_parts: Any
    model: str


@dataclass
class SearchAnswer:
    text: str
    sources: list[dict[str, str]]


class AIProvider(Protocol):
    name: str

    def generate(self, *, system: str, turns: list[Turn], tools: list[ToolDeclaration]) -> ModelReply:
        """Gera a próxima resposta do modelo. Pode devolver chamadas de ferramenta."""
        ...

    def web_search(self, query: str) -> SearchAnswer:
        """Pesquisa na web com fontes citadas. Nunca deve inventar fontes."""
        ...
