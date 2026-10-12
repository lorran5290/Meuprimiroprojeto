"""Fonte de áudio do microfone (sounddevice) e modelo de reconhecimento (Vosk).

Ambos são dependências opcionais (requirements-voice.txt). Sem elas, o LS
continua funcionando por texto e informa que a voz está indisponível.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ls_assistant.errors import LSError

SAMPLE_RATE = 16_000
BLOCK_SAMPLES = 4_000  # 250 ms por bloco


def load_vosk_model(path: str) -> Any:
    model_dir = Path(path).expanduser()
    if not model_dir.is_dir():
        raise LSError(
            f"Modelo de voz não encontrado em '{model_dir}'. Baixe um modelo pt-BR do Vosk "
            "e aponte LS_VOSK_MODEL_PATH para a pasta dele."
        )
    try:
        from vosk import Model, SetLogLevel
    except ImportError as exc:
        raise LSError("Voz requer o pacote vosk. Rode: pip install -r requirements-voice.txt") from exc
    SetLogLevel(-1)
    return Model(str(model_dir))


def microphone_chunks(device: str | None, stop: threading.Event) -> Iterator[bytes]:
    """Gera blocos PCM 16 bits mono enquanto ``stop`` não estiver marcado."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise LSError("Microfone requer o pacote sounddevice. Rode: pip install -r requirements-voice.txt") from exc

    blocks: queue.Queue[bytes] = queue.Queue(maxsize=50)

    def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
        try:
            blocks.put_nowait(bytes(indata))
        except queue.Full:
            pass  # se o laço estiver atrasado, descarta áudio antigo em vez de travar

    try:
        stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=BLOCK_SAMPLES, device=device or None,
            dtype="int16", channels=1, callback=callback,
        )
    except Exception as exc:  # PortAudio/dispositivo inexistente
        raise LSError(f"Não consegui abrir o microfone: {exc}") from exc

    with stream:
        while not stop.is_set():
            try:
                yield blocks.get(timeout=0.5)
            except queue.Empty:
                continue


def list_microphones() -> list[str]:
    try:
        import sounddevice as sd
    except ImportError:
        return []
    names = []
    for index, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            names.append(f"{index}: {dev['name']}")
    return names
