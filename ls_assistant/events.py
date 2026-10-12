"""Barramento de eventos: o núcleo publica, a interface assina.

Usado para estado do núcleo (ESCUTANDO, PROCESSANDO...), progresso de
ferramentas, mensagens e pedidos de confirmação. Thread-safe.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

Subscriber = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self, history_size: int = 300) -> None:
        self._subscribers: list[Subscriber] = []
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "type": kind, "ts": time.time(), "payload": payload or {}}
            self._history.append(event)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception:  # um cliente com erro não derruba o núcleo
                pass
        return event

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return unsubscribe

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._history)
        return items[-limit:]
