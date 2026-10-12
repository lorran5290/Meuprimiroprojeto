"""Configuração do LS.

Ordem de precedência (a última vence):
    valores padrão  <  settings.json (preferências salvas pela interface)
                    <  arquivo .env  <  variáveis de ambiente do sistema

Segredos (GEMINI_API_KEY) só entram por .env ou variável de ambiente.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from ls_assistant.errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Modelo verificado em testes reais (ver docs/STATUS_TESTES.md).
# gemini-2.5-flash foi descontinuado para novos usuários.
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_FALLBACK_MODELS: tuple[str, ...] = ("gemini-3.8-flash",)
DEFAULT_WAKE_WORDS: tuple[str, ...] = ("ls", "ele esse", "elesse")

# Campos que podem ser salvos pela interface em settings.json.
EDITABLE_FIELDS: tuple[str, ...] = (
    "gemini_model",
    "keep_history",
    "voice_enabled",
    "wake_word_enabled",
    "tts_enabled",
    "tts_voice",
    "tts_rate",
    "tts_volume",
    "effects_intensity",
    "autostart",
)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = None
    gemini_model: str = DEFAULT_MODEL
    gemini_fallback_models: tuple[str, ...] = DEFAULT_FALLBACK_MODELS
    gemini_timeout_s: float = 60.0

    data_dir: Path = Path(".ls-data")
    allowed_roots: tuple[Path, ...] = ()

    server_host: str = "127.0.0.1"
    server_port: int = 0  # 0 = porta livre escolhida pelo sistema
    log_level: str = "INFO"
    tool_timeout_s: float = 30.0
    confirmation_timeout_s: float = 120.0
    keep_history: bool = True

    voice_enabled: bool = False
    wake_word_enabled: bool = False
    wake_words: tuple[str, ...] = DEFAULT_WAKE_WORDS
    vosk_model_path: str | None = None
    mic_device: str | None = None
    tts_enabled: bool = True
    tts_voice: str | None = None
    tts_rate: int = 0
    tts_volume: int = 100

    effects_intensity: float = 1.0
    autostart: bool = False

    # Caminhos derivados de data_dir -------------------------------------
    @property
    def memory_db(self) -> Path:
        return self.data_dir / "ls_memoria.sqlite3"

    @property
    def audit_db(self) -> Path:
        return self.data_dir / "ls_auditoria.sqlite3"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def plans_dir(self) -> Path:
        return self.data_dir / "planos"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_dir / "quarentena"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def secret_values(self) -> list[str]:
        """Valores sensíveis que nunca podem aparecer em logs."""
        return [self.gemini_api_key] if self.gemini_api_key else []

    def public_dict(self) -> dict[str, Any]:
        """Versão sem segredos, para a interface e para diagnóstico."""
        data: dict[str, Any] = {}
        for f in fields(self):
            if f.name in {"gemini_api_key"}:
                continue
            value = getattr(self, f.name)
            if isinstance(value, Path):
                value = str(value)
            elif isinstance(value, tuple):
                value = [str(v) for v in value]
            data[f.name] = value
        data["gemini_api_key_configured"] = bool(self.gemini_api_key)
        return data


def _default_data_dir(env: Mapping[str, str]) -> Path:
    if env.get("LS_DATA_DIR"):
        return Path(env["LS_DATA_DIR"]).expanduser()
    if os.name == "nt":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "LS"
    return Path.home() / ".local" / "share" / "ls-assistant"


def _default_roots() -> tuple[Path, ...]:
    home = Path.home()
    return tuple(home / name for name in ("Desktop", "Documents", "Downloads", "Pictures"))


def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "sim"}


def _to_tuple(raw: Any, sep: str = ",") -> tuple[str, ...]:
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        items = str(raw).split(sep)
    return tuple(item.strip() for item in items if item.strip())


# Mapa: variável de ambiente -> (campo, conversor)
_ENV_MAP: dict[str, tuple[str, Any]] = {
    "GEMINI_API_KEY": ("gemini_api_key", str),
    "GEMINI_MODEL": ("gemini_model", str),
    "GEMINI_FALLBACK_MODELS": ("gemini_fallback_models", _to_tuple),
    "GEMINI_TIMEOUT_S": ("gemini_timeout_s", float),
    "LS_ALLOWED_ROOTS": ("allowed_roots", lambda raw: tuple(Path(p).expanduser() for p in _to_tuple(raw, ";"))),
    "LS_HOST": ("server_host", str),
    "LS_PORT": ("server_port", int),
    "LS_LOG_LEVEL": ("log_level", lambda raw: str(raw).upper()),
    "LS_TOOL_TIMEOUT_S": ("tool_timeout_s", float),
    "LS_CONFIRMATION_TIMEOUT_S": ("confirmation_timeout_s", float),
    "LS_KEEP_HISTORY": ("keep_history", _to_bool),
    "LS_VOICE_ENABLED": ("voice_enabled", _to_bool),
    "LS_WAKE_WORD_ENABLED": ("wake_word_enabled", _to_bool),
    "LS_WAKE_WORDS": ("wake_words", _to_tuple),
    "LS_VOSK_MODEL_PATH": ("vosk_model_path", str),
    "LS_MIC_DEVICE": ("mic_device", str),
    "LS_TTS_ENABLED": ("tts_enabled", _to_bool),
    "LS_TTS_VOICE": ("tts_voice", str),
    "LS_TTS_RATE": ("tts_rate", int),
    "LS_TTS_VOLUME": ("tts_volume", int),
    "LS_EFFECTS_INTENSITY": ("effects_intensity", float),
    "LS_AUTOSTART": ("autostart", _to_bool),
}


def read_settings_file(path: Path) -> dict[str, Any]:
    """Lê settings.json, ignorando campos desconhecidos ou corrompidos."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in EDITABLE_FIELDS}


def load_settings(
    env: Mapping[str, str] | None = None,
    *,
    dotenv_path: Path | None = PROJECT_ROOT / ".env",
) -> Settings:
    """Monta a configuração final.

    Com ``env=None`` lê o .env do projeto e o ambiente do sistema.
    Testes passam um dicionário explícito e ``dotenv_path=None``.
    """
    if env is None:
        merged: dict[str, str] = {}
        if dotenv_path is not None and dotenv_path.exists():
            merged.update({k: v for k, v in dotenv_values(dotenv_path).items() if v is not None})
        merged.update(os.environ)
        env = merged

    data_dir = _default_data_dir(env)
    values: dict[str, Any] = {
        "data_dir": data_dir,
        "allowed_roots": _default_roots(),
    }
    values.update(read_settings_file(data_dir / "settings.json"))

    for var, (field_name, convert) in _ENV_MAP.items():
        raw = env.get(var)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            values[field_name] = convert(raw.strip() if isinstance(raw, str) else raw)
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"Valor inválido em {var}: {exc}") from exc

    if isinstance(values.get("wake_words"), list):
        values["wake_words"] = tuple(values["wake_words"])
    if isinstance(values.get("gemini_fallback_models"), list):
        values["gemini_fallback_models"] = tuple(values["gemini_fallback_models"])
    if isinstance(values.get("allowed_roots"), list):
        values["allowed_roots"] = tuple(Path(p) for p in values["allowed_roots"])

    values["effects_intensity"] = min(1.0, max(0.0, float(values.get("effects_intensity", 1.0))))
    values["tts_volume"] = min(100, max(0, int(values.get("tts_volume", 100))))
    values["tts_rate"] = min(10, max(-10, int(values.get("tts_rate", 0))))
    values["data_dir"] = Path(values["data_dir"])
    return Settings(**values)
