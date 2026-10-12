"""Histórico da conversa em curso, com limite de tamanho seguro.

A poda acontece somente no início de um turno de usuário, para nunca separar
uma chamada de função da sua resposta (o Gemini exige o par).
"""

from __future__ import annotations

import threading

from ls_assistant.ai.base import Turn


class Conversation:
    def __init__(self, max_turns: int = 60) -> None:
        self._turns: list[Turn] = []
        self._max_turns = max_turns
        self._lock = threading.Lock()

    def add(self, turn: Turn) -> None:
        with self._lock:
            self._turns.append(turn)
            self._trim()

    def turns(self) -> list[Turn]:
        with self._lock:
            return list(self._turns)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._turns)

    def _trim(self) -> None:
        if len(self._turns) <= self._max_turns:
            return
        excess = len(self._turns) - self._max_turns
        # Procura o primeiro turno de usuário a partir do ponto de corte.
        for index in range(excess, len(self._turns)):
            if self._turns[index].role == "user":
                del self._turns[:index]
                return
        self._turns.clear()
