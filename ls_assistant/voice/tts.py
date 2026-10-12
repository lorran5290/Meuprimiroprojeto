"""Síntese de voz (fala do LS).

Implementação inicial: ``WindowsSpeechTTS`` usa o System.Speech do Windows
(vozes instaladas, incluindo português do Brasil), sem dependências extras e sem nuvem.
A interrupção é imediata: o processo do PowerShell é encerrado.

Para trocar de motor, implemente ``TTSEngine`` em outro arquivo.
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import sys
import threading
from typing import Protocol

log = logging.getLogger(__name__)

# O texto entra por stdin (UTF-8). Rate, volume e voz entram por variáveis de ambiente,
# para que nada vindo do usuário seja interpolado em código.
_SPEAK_SCRIPT = r"""
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$text = [Console]::In.ReadToEnd()
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $synth.Rate = [int]$env:LS_TTS_RATE
  $synth.Volume = [int]$env:LS_TTS_VOLUME
  if ($env:LS_TTS_VOICE) { try { $synth.SelectVoice($env:LS_TTS_VOICE) } catch { } }
  $synth.Speak($text)
} finally { $synth.Dispose() }
"""

_LIST_VOICES_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name } }
finally { $synth.Dispose() }
"""

_CREATE_NO_WINDOW = 0x08000000


def _encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


class TTSEngine(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def speaking(self) -> bool: ...
    def speak(self, text: str) -> bool: ...
    def stop(self) -> None: ...
    def list_voices(self) -> list[dict[str, str]]: ...


class NullTTS:
    """Usado quando não há síntese de voz: o LS responde só por texto."""

    available = False
    speaking = False

    def speak(self, text: str) -> bool:
        return False

    def stop(self) -> None:
        return None

    def list_voices(self) -> list[dict[str, str]]:
        return []


class WindowsSpeechTTS:
    def __init__(self, *, voice: str | None = None, rate: int = 0, volume: int = 100) -> None:
        if sys.platform != "win32":
            raise RuntimeError("System.Speech só existe no Windows.")
        self._voice = voice or ""
        self._rate = max(-10, min(10, rate))
        self._volume = max(0, min(100, volume))
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return True

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def configure(self, *, voice: str | None, rate: int, volume: int) -> None:
        self._voice = voice or ""
        self._rate = max(-10, min(10, rate))
        self._volume = max(0, min(100, volume))

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update({"LS_TTS_RATE": str(self._rate), "LS_TTS_VOLUME": str(self._volume), "LS_TTS_VOICE": self._voice})
        return env

    def speak(self, text: str) -> bool:
        """Fala o texto e espera terminar. Retorna False se foi interrompida ou falhou."""
        text = text.strip()
        if not text:
            return False
        command = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-EncodedCommand", _encoded(_SPEAK_SCRIPT)]
        try:
            proc = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                env=self._env(), creationflags=_CREATE_NO_WINDOW,
            )
        except OSError:
            log.exception("Não consegui iniciar o motor de voz")
            return False
        with self._lock:
            self._proc = proc
        try:
            proc.communicate(input=text.encode("utf-8"), timeout=max(30, len(text) / 5))
        except subprocess.TimeoutExpired:
            proc.kill()
            return False
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        return proc.returncode == 0

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()

    def list_voices(self) -> list[dict[str, str]]:
        command = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-EncodedCommand", _encoded(_LIST_VOICES_SCRIPT)]
        try:
            out = subprocess.run(command, capture_output=True, text=True, timeout=20, creationflags=_CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return []
        voices = []
        for line in out.stdout.splitlines():
            name, _, culture = line.partition("|")
            if name.strip():
                voices.append({"nome": name.strip(), "idioma": culture.strip()})
        return voices


def build_tts(enabled: bool, *, voice: str | None, rate: int, volume: int) -> TTSEngine:
    if not enabled or sys.platform != "win32":
        return NullTTS()
    return WindowsSpeechTTS(voice=voice, rate=rate, volume=volume)
