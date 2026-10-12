"""Níveis de risco das ferramentas e regra de decisão.

Regra central: o modelo de IA só *pede* ações. Quem decide é o executor,
usando o nível de risco declarado por cada ferramenta.

- READ        : não altera nada. Executa automaticamente.
- REVERSIBLE  : altera algo que pode ser desfeito. Executa automaticamente.
- CONFIRM     : exclusão/fechamento/captura/aplicação de planos. Exige aprovação.
- EXTERNAL    : envia, publica, compra ou age fora do computador. Exige aprovação explícita.
- BLOCKED     : nunca executada pelo assistente.
"""

from __future__ import annotations

from enum import Enum


class Risk(str, Enum):
    READ = "leitura"
    REVERSIBLE = "reversivel"
    CONFIRM = "confirmacao"
    EXTERNAL = "externo"
    BLOCKED = "bloqueado"

    @property
    def needs_approval(self) -> bool:
        return self in (Risk.CONFIRM, Risk.EXTERNAL)


def decide(risk: Risk) -> str:
    """Retorna 'auto', 'ask' ou 'deny' para um nível de risco."""
    if risk is Risk.BLOCKED:
        return "deny"
    if risk.needs_approval:
        return "ask"
    return "auto"
