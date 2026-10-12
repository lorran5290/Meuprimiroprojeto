"""Preferências do usuário: validação e persistência em settings.json.

Somente campos listados em ``EDITABLE_FIELDS`` podem ser alterados pela interface.
Segredos e caminhos de sistema não passam por aqui.
"""

from __future__ import annotations

import dataclasses
import json
import re
import threading
from pathlib import Path
from typing import Any

from ls_assistant.config import EDITABLE_FIELDS, Settings
from ls_assistant.errors import LSError

_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{2,79}$")


def _validate(name: str, value: Any) -> Any:
    if name == "gemini_model":
        if not isinstance(value, str) or not _MODEL_RE.match(value):
            raise LSError("Nome de modelo inválido. Exemplo: gemini-3.5-flash.")
        return value
    if name in {"keep_history", "voice_enabled", "wake_word_enabled", "tts_enabled", "autostart"}:
        if not isinstance(value, bool):
            raise LSError(f"'{name}' deve ser verdadeiro ou falso.")
        return value
    if name == "tts_voice":
        if value in (None, ""):
            return None
        if not isinstance(value, str) or len(value) > 120:
            raise LSError("Nome de voz inválido.")
        return value
    if name == "tts_rate":
        if not isinstance(value, int) or not -10 <= value <= 10:
            raise LSError("Velocidade da fala deve estar entre -10 e 10.")
        return value
    if name == "tts_volume":
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise LSError("Volume deve estar entre 0 e 100.")
        return value
    if name == "effects_intensity":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
            raise LSError("Intensidade dos efeitos deve estar entre 0 e 1.")
        return float(value)
    raise LSError(f"Campo '{name}' não pode ser alterado pela interface.")


class SettingsService:
    def __init__(self, settings: Settings, file: Path) -> None:
        self._settings = settings
        self._file = file
        self._lock = threading.Lock()

    @property
    def current(self) -> Settings:
        return self._settings

    def update(self, changes: dict[str, Any]) -> Settings:
        unknown = set(changes) - set(EDITABLE_FIELDS)
        if unknown:
            raise LSError(f"Campos não editáveis: {', '.join(sorted(unknown))}.")
        clean = {name: _validate(name, value) for name, value in changes.items()}
        with self._lock:
            stored = self._read_file()
            stored.update(clean)
            self._file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._file.with_suffix(".tmp")
            tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._file)
            self._settings = dataclasses.replace(self._settings, **clean)
        return self._settings

    def _read_file(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in raw.items() if k in EDITABLE_FIELDS} if isinstance(raw, dict) else {}
