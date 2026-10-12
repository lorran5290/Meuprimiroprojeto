"""Catálogo de ferramentas disponíveis. Ponto único para adicionar habilidades."""

from __future__ import annotations

from typing import Any

from ls_assistant.ai.base import ToolDeclaration
from ls_assistant.tools.base import ToolSpec


def _strip_titles(schema: Any) -> Any:
    """Remove chaves 'title' geradas pelo Pydantic; o modelo só precisa de tipos e descrições."""
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Ferramenta duplicada: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[n] for n in self.names()]

    def declarations(self) -> list[ToolDeclaration]:
        out: list[ToolDeclaration] = []
        for spec in self.specs():
            schema = _strip_titles(spec.args_model.model_json_schema())
            schema.setdefault("type", "object")
            schema.setdefault("properties", {})
            out.append(ToolDeclaration(name=spec.name, description=spec.description, parameters=schema))
        return out

    def catalog(self) -> list[dict[str, Any]]:
        """Descrição legível para a interface (painel de ferramentas)."""
        return [
            {"name": s.name, "title": s.title, "risk": s.risk.value, "description": s.description}
            for s in self.specs()
        ]
