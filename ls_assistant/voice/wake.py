"""Palavra de ativação ("LS") e controle de falsos acionamentos.

- Compara palavras inteiras (não substrings): "lsbo" não dispara, "ls" dispara.
- Cooldown: após acionar, ignora novos acionamentos por alguns segundos.
- A gramática enviada ao reconhecedor contém só as palavras de ativação e [unk],
  o que reduz muito o ruído de reconhecimento.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable

from ls_assistant.memory.store import normalize


class WakeWordMatcher:
    def __init__(
        self,
        phrases: Iterable[str],
        *,
        cooldown_s: float = 2.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._phrases = tuple(p for p in (normalize(x) for x in phrases) if p)
        if not self._phrases:
            raise ValueError("Informe pelo menos uma palavra de ativação.")
        self._cooldown = cooldown_s
        self._clock = clock
        self._last_trigger: float | None = None

    @property
    def phrases(self) -> tuple[str, ...]:
        return self._phrases

    def grammar(self) -> list[str]:
        """Lista usada pelo Vosk para restringir o reconhecimento."""
        return [*self._phrases, "[unk]"]

    def matches(self, text: str) -> bool:
        words = re.findall(r"[a-z0-9]+", normalize(text))
        for phrase in self._phrases:
            size = len(phrase.split())
            for i in range(len(words) - size + 1):
                if " ".join(words[i : i + size]) == phrase:
                    return True
        return False

    def try_trigger(self, text: str) -> bool:
        """True se a fala contém a palavra de ativação e o cooldown já passou."""
        if not self.matches(text):
            return False
        now = self._clock()
        if self._last_trigger is not None and now - self._last_trigger < self._cooldown:
            return False
        self._last_trigger = now
        return True

    def strip_wake(self, text: str) -> str:
        """Remove a palavra de ativação do início do comando ('LS, abra o navegador' -> 'abra o navegador')."""
        original = text.strip()
        words = original.split()
        normalized_words = [normalize(w).strip(",.!?;:") for w in words]
        for phrase in self._phrases:
            size = len(phrase.split())
            if " ".join(normalized_words[:size]) == phrase:
                rest = " ".join(words[size:]).lstrip(" ,.:;-")
                return rest
        return original
