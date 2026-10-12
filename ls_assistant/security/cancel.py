"""Token de cancelamento cooperativo usado por tarefas, ferramentas e voz."""

from __future__ import annotations

import threading

from ls_assistant.errors import ActionCancelled


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason = ""

    def cancel(self, reason: str = "cancelado pelo usuário") -> None:
        self.reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise ActionCancelled(self.reason or "cancelado")

    def wait(self, timeout: float) -> bool:
        """Espera até ``timeout`` segundos; devolve True se foi cancelado."""
        return self._event.wait(timeout)
