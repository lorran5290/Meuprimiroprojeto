"""Tipos do sistema de ferramentas.

Cada ferramenta declara: nome, descrição para o modelo, argumentos tipados
(Pydantic), nível de risco, limite de tempo e como descrever a ação para o usuário.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ls_assistant.ai.base import ImageInput
from ls_assistant.errors import LSError
from ls_assistant.security.cancel import CancelToken
from ls_assistant.security.permissions import Risk


class ToolUnavailable(LSError):
    """A ferramenta depende de um serviço ou recurso que não está disponível agora."""


class ToolUnverified(LSError):
    """O pedido foi enviado, mas o resultado não pôde ser confirmado. Nunca é tratado como sucesso."""


@dataclass
class ActionResult:
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    images: list[ImageInput] = field(default_factory=list)


@dataclass
class ToolContext:
    cancel: CancelToken


Handler = Callable[[Any, ToolContext], ActionResult]


@dataclass
class ToolSpec:
    name: str
    title: str
    description: str
    risk: Risk
    args_model: type[BaseModel]
    handler: Handler
    timeout_s: float | None = None
    describe: Callable[[Any], str] | None = None


@dataclass
class ToolOutcome:
    tool: str
    # ok | unverified | failed | invalid_args | unknown_tool | denied | cancelled | timeout | unavailable
    status: str
    message: str
    risk: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    images: list[ImageInput] = field(default_factory=list)
    duration_ms: int = 0
    approval: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_model_dict(self) -> dict[str, Any]:
        """O que o modelo recebe de volta. Só informações necessárias ao raciocínio."""
        return {"status": self.status, "message": self.message, "data": self.data}

    def to_event(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status,
            "message": self.message,
            "risk": self.risk,
            "duration_ms": self.duration_ms,
            "approval": self.approval,
        }
