"""Logs do LS com redação automática de segredos.

Nenhuma linha de log deve conter a chave da API. O filtro remove
valores conhecidos e qualquer padrão com cara de chave Google.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_KEY_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{10,}"),
)
REDACTED = "[segredo-oculto]"


class SecretFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self._secrets = [s for s in (secrets or []) if s]

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        for pattern in _KEY_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str, logs_dir: Path, secrets: list[str] | None = None) -> logging.Logger:
    """Configura o logger raiz: console + arquivo rotativo em logs_dir."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Evita handlers duplicados quando a função é chamada de novo (ex.: testes).
    for handler in list(root.handlers):
        if getattr(handler, "_ls_handler", False):
            root.removeHandler(handler)

    secret_filter = SecretFilter(secrets)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(logs_dir / "ls.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    console = logging.StreamHandler()
    for handler in (file_handler, console):
        handler.setFormatter(fmt)
        handler.addFilter(secret_filter)
        handler._ls_handler = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    # Bibliotecas HTTP registram cada requisição em INFO; isso só polui o log.
    for noisy in ("httpx", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return root
