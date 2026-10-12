"""Máquina de estados do microfone: espera -> acordado -> comando -> espera.

``feed(chunk)`` processa um bloco de áudio PCM 16 bits mono (síncrono e testável).
``start(source)`` roda o mesmo laço numa thread, consumindo blocos de uma fonte.

Reconhecedores são injetados (Protocol compatível com o Vosk), então a lógica
pode ser testada sem microfone nem modelo de voz.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from array import array
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from ls_assistant.voice.wake import WakeWordMatcher

log = logging.getLogger(__name__)

STANDBY, AWAKE = "espera", "acordado"


class Recognizer(Protocol):
    def AcceptWaveform(self, data: bytes) -> bool: ...
    def Result(self) -> str: ...
    def PartialResult(self) -> str: ...
    def FinalResult(self) -> str: ...


def rms(chunk: bytes) -> float:
    """Energia média do bloco (int16). Usada como filtro de ruído/silêncio."""
    samples = array("h")
    samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def _text_of(payload: str, key: str) -> str:
    try:
        return str(json.loads(payload).get(key, "")).strip()
    except (ValueError, AttributeError):
        return ""


class VoiceListener:
    def __init__(
        self,
        *,
        make_wake_recognizer: Callable[[], Recognizer],
        make_command_recognizer: Callable[[], Recognizer],
        matcher: WakeWordMatcher,
        on_wake: Callable[[], None],
        on_command: Callable[[str], None],
        on_state: Callable[[str], None] = lambda state: None,
        energy_threshold: float = 300.0,
        command_timeout_s: float = 8.0,
        wake_enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._make_wake = make_wake_recognizer
        self._make_command = make_command_recognizer
        self._matcher = matcher
        self._on_wake = on_wake
        self._on_command = on_command
        self._on_state = on_state
        self._threshold = energy_threshold
        self._command_timeout = command_timeout_s
        self._wake_enabled = wake_enabled
        self._clock = clock

        self._state = STANDBY
        self._wake_rec: Recognizer | None = None
        self._command_rec: Recognizer | None = None
        self._awake_since = 0.0
        self._button_requested = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # RLock: on_command pode, em tese, chamar métodos do próprio ouvinte.
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        return self._state

    # Controle externo ---------------------------------------------------------
    def request_command(self) -> None:
        """Modo botão: escuta um comando sem precisar da palavra de ativação."""
        with self._lock:
            self._button_requested = True

    def cancel_command(self) -> None:
        with self._lock:
            self._button_requested = False
            self._set_state(STANDBY)
            self._command_rec = None

    def start(self, source: Iterable[bytes]) -> None:
        if self._thread is not None:
            raise RuntimeError("O ouvinte já está em execução.")
        self._stop.clear()

        def run() -> None:
            try:
                for chunk in source:
                    if self._stop.is_set():
                        break
                    self.feed(chunk)
            except Exception:  # falha de áudio não pode derrubar o aplicativo
                log.exception("Falha no microfone")
                self._set_state("erro")
            finally:
                self._set_state("desligado")

        self._thread = threading.Thread(target=run, name="ls-voice-listener", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        self._wake_rec = None
        self._command_rec = None
        self._set_state("desligado")

    # Processamento -----------------------------------------------------------------
    def feed(self, chunk: bytes) -> None:
        with self._lock:
            if self._button_requested and self._state == STANDBY:
                self._button_requested = False
                self._enter_awake()
            if self._state == AWAKE:
                self._feed_command(chunk)
            else:
                self._feed_wake(chunk)

    def _feed_wake(self, chunk: bytes) -> None:
        if not self._wake_enabled or rms(chunk) < self._threshold:
            return  # palavra de ativação desligada, silêncio ou ruído baixo
        if self._wake_rec is None:
            self._wake_rec = self._make_wake()
        rec = self._wake_rec
        text = _text_of(rec.Result(), "text") if rec.AcceptWaveform(chunk) else _text_of(rec.PartialResult(), "partial")
        if text and self._matcher.try_trigger(text):
            self._wake_rec = None  # recomeça limpo depois do comando
            self._on_wake()
            self._enter_awake()

    def _enter_awake(self) -> None:
        self._command_rec = self._make_command()
        self._awake_since = self._clock()
        self._set_state(AWAKE)

    def _feed_command(self, chunk: bytes) -> None:
        if self._command_rec is None:
            self._command_rec = self._make_command()
        rec = self._command_rec
        if rec.AcceptWaveform(chunk):
            text = self._matcher.strip_wake(_text_of(rec.Result(), "text"))
            self._command_rec = None
            if text:
                self._set_state("ouvindo")
                self._set_state(STANDBY)
                self._on_command(text)
                return
            self._set_state(STANDBY)
            return
        if self._clock() - self._awake_since > self._command_timeout:
            partial = _text_of(rec.FinalResult(), "text")
            self._command_rec = None
            self._set_state(STANDBY)
            if partial:
                self._on_command(self._matcher.strip_wake(partial))

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self._on_state(state)


def vosk_recognizer_factory(model: Any, sample_rate: int, grammar: list[str] | None) -> Callable[[], Recognizer]:
    """Cria fábrica de reconhecedores Vosk (com ou sem gramática restrita)."""

    def make() -> Recognizer:
        from vosk import KaldiRecognizer  # importado sob demanda: o pacote é opcional

        if grammar:
            return KaldiRecognizer(model, sample_rate, json.dumps(grammar, ensure_ascii=False))
        return KaldiRecognizer(model, sample_rate)

    return make
