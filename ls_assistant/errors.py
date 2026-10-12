"""Exceções do LS. Mensagens são escritas para serem mostradas ao usuário."""

from __future__ import annotations


class LSError(Exception):
    """Erro base. A mensagem é segura para exibir na interface."""


class ConfigError(LSError):
    """Configuração inválida ou ausente."""


class AIUnavailableError(LSError):
    """O serviço de IA não pôde responder.

    ``kind`` classifica a causa para o chamador decidir o que fazer:
    ``quota``, ``unavailable``, ``auth``, ``invalid_request``, ``network``,
    ``model_unavailable`` ou ``unknown``.
    """

    def __init__(self, message: str, *, kind: str = "unknown", retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


class ActionCancelled(LSError):
    """A tarefa foi cancelada (pelo usuário ou pela parada de emergência)."""


class ActionDenied(LSError):
    """A ação foi recusada pelo usuário, pelo tempo limite ou pela política de segurança."""


class PathNotAllowed(LSError):
    """O caminho está fora das pastas permitidas ou em local protegido do sistema."""
