"""Coordena microfone, palavra de ativação, fala e interrupção.

Estados publicados na interface:
- desligado : microfone desligado pelo usuário (ou indisponível)
- espera    : escutando só a palavra de ativação
- acordado  : ouvindo um comando
- ouvindo   : comando capturado
- falando   : o LS está falando
- erro      : falha no áudio
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ls_assistant.errors import LSError
from ls_assistant.events import EventBus
from ls_assistant.voice import mic
from ls_assistant.voice.listener import VoiceListener, vosk_recognizer_factory
from ls_assistant.voice.tts import TTSEngine
from ls_assistant.voice.wake import WakeWordMatcher

log = logging.getLogger(__name__)


class VoiceController:
    def __init__(
        self,
        *,
        tts: TTSEngine,
        events: EventBus,
        on_command: Callable[[str], None],
        wake_words: tuple[str, ...],
        vosk_model_path: str | None,
        mic_device: str | None,
        wake_word_enabled: bool,
    ) -> None:
        self._tts = tts
        self._events = events
        self._on_command = on_command
        self._wake_words = wake_words
        self._model_path = vosk_model_path
        self._mic_device = mic_device
        self._wake_enabled = wake_word_enabled
        self._listener: VoiceListener | None = None
        self._mic_on = False
        self._mic_error: str | None = None
        self._model = None
        self._stop_audio = threading.Event()
        self._lock = threading.Lock()

    # Estado -----------------------------------------------------------------
    @property
    def mic_on(self) -> bool:
        return self._mic_on

    @property
    def speaking(self) -> bool:
        return self._tts.speaking

    @property
    def tts_available(self) -> bool:
        return self._tts.available

    def status(self) -> dict[str, object]:
        return {
            "microfone": "ligado" if self._mic_on else "desligado",
            "palavra_de_ativacao": self._wake_enabled,
            "palavras_de_ativacao": list(self._wake_words),
            "fala_disponivel": self._tts.available,
            "falando": self.speaking,
            "erro": self._mic_error,
        }

    # Microfone ------------------------------------------------------------------
    def set_microphone(self, enabled: bool) -> dict[str, object]:
        with self._lock:
            if enabled:
                self._start_listening()
            else:
                self._stop_listening()
        return self.status()

    def set_wake_enabled(self, enabled: bool) -> None:
        """Liga/desliga a palavra de ativação. Se o microfone estiver ligado, reinicia a escuta."""
        if enabled == self._wake_enabled:
            return
        self._wake_enabled = enabled
        if self._mic_on:
            with self._lock:
                self._stop_listening()
                try:
                    self._start_listening()
                except LSError:
                    # _start_listening já publicou o erro; a preferência foi salva mesmo assim.
                    log.warning("Não consegui reiniciar a escuta com a nova preferência de palavra de ativação")

    def talk_once(self) -> dict[str, object]:
        """Botão 'falar': captura um comando sem palavra de ativação. Liga o microfone se preciso."""
        with self._lock:
            if not self._mic_on:
                self._start_listening()
            if self._listener is not None:
                self._listener.request_command()
        return self.status()

    def _start_listening(self) -> None:
        self._mic_error = None
        try:
            if self._model is None:
                if not self._model_path:
                    raise LSError("Voz não configurada: defina LS_VOSK_MODEL_PATH com a pasta de um modelo Vosk pt-BR.")
                self._model = mic.load_vosk_model(self._model_path)
            matcher = WakeWordMatcher(self._wake_words)
            self._stop_audio.clear()
            self._listener = VoiceListener(
                make_wake_recognizer=vosk_recognizer_factory(self._model, mic.SAMPLE_RATE, matcher.grammar()),
                make_command_recognizer=vosk_recognizer_factory(self._model, mic.SAMPLE_RATE, None),
                matcher=matcher,
                on_wake=lambda: self._events.emit("voice", {"event": "wake"}),
                on_command=self._handle_command,
                on_state=lambda state: self._events.emit("voice", {"event": "state", "state": state}),
                wake_enabled=self._wake_enabled,
            )
            # O áudio sempre flui enquanto o microfone está ligado (necessário também para o botão 'falar').
            source = mic.microphone_chunks(self._mic_device, self._stop_audio)
            self._listener.start(source)
            self._mic_on = True
            self._events.emit("voice", {"event": "mic", "on": True})
        except LSError as exc:
            self._mic_error = str(exc)
            self._mic_on = False
            self._events.emit("voice", {"event": "error", "message": str(exc)})
            raise

    def _stop_listening(self) -> None:
        self._stop_audio.set()
        if self._listener is not None:
            self._listener.stop()
        self._listener = None
        self._mic_on = False
        self._events.emit("voice", {"event": "mic", "on": False})

    def _handle_command(self, text: str) -> None:
        self._events.emit("voice", {"event": "command", "text": text})
        self._on_command(text)

    # Fala ----------------------------------------------------------------------
    def speak(self, text: str, on_done: Callable[[], None] | None = None) -> None:
        """Fala em segundo plano. Não bloqueia a interface."""
        if not self._tts.available or not text.strip():
            if on_done:
                on_done()
            return
        self._events.emit("voice", {"event": "speaking", "on": True})

        def run() -> None:
            try:
                self._tts.speak(text)
            finally:
                self._events.emit("voice", {"event": "speaking", "on": False})
                if on_done:
                    on_done()

        threading.Thread(target=run, name="ls-tts", daemon=True).start()

    def interrupt_speech(self) -> bool:
        """Interrompe a fala imediatamente. Retorna True se havia fala em andamento."""
        was = self.speaking
        self._tts.stop()
        return was

    def shutdown(self) -> None:
        with self._lock:
            self._stop_listening()
        self.interrupt_speech()
