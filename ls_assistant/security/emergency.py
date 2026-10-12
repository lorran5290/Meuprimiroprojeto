"""Parada de emergência: cancela tudo o que o LS está fazendo.

Ao acionar:
- cancela tarefas ativas (cancelamento cooperativo);
- recusa todas as aprovações pendentes;
- chama os retornos registrados (ex.: interromper a fala).
Novas ações são bloqueadas até ``reset``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ls_assistant.security.cancel import CancelToken
from ls_assistant.security.confirmations import ConfirmationBroker

log = logging.getLogger(__name__)


class EmergencyStop:
    def __init__(self, broker: ConfirmationBroker) -> None:
        self._broker = broker
        self._tokens: list[CancelToken] = []
        self._hooks: list[Callable[[], None]] = []
        self._active = threading.Event()
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self._active.is_set()

    def new_token(self) -> CancelToken:
        token = CancelToken()
        with self._lock:
            self._tokens = [t for t in self._tokens if not t.cancelled]
            self._tokens.append(token)
        if self.active:
            token.cancel("parada de emergência ativa")
        return token

    def add_hook(self, hook: Callable[[], None]) -> None:
        self._hooks.append(hook)

    def trigger(self, reason: str = "parada de emergência acionada pelo usuário") -> dict[str, int]:
        self._active.set()
        with self._lock:
            tokens = list(self._tokens)
        for token in tokens:
            token.cancel(reason)
        denied = self._broker.cancel_all(reason)
        for hook in self._hooks:
            try:
                hook()
            except Exception:  # um gancho com erro não pode impedir a parada
                log.exception("Falha em gancho da parada de emergência")
        log.warning("Parada de emergência: %s tarefas canceladas, %s aprovações recusadas", len(tokens), denied)
        return {"tasks_cancelled": len(tokens), "approvals_denied": denied}

    def reset(self) -> None:
        self._active.clear()
