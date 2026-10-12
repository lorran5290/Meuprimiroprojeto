"""Captura de tela sob demanda.

Não há monitoramento contínuo. Cada captura é uma chamada explícita e exige
aprovação (risco CONFIRM). A imagem é reduzida antes de ser enviada ao modelo.
"""

from __future__ import annotations

import io

from ls_assistant.tools.base import ToolUnavailable


def capture_screen_png(max_side: int = 1600) -> bytes:
    try:
        from PIL import Image, ImageGrab
    except ImportError as exc:  # pragma: no cover - depende da instalação
        raise ToolUnavailable("Captura de tela requer o pacote Pillow.") from exc
    try:
        image = ImageGrab.grab(all_screens=True)
    except (OSError, ValueError, NotImplementedError) as exc:
        raise ToolUnavailable(f"Não consegui capturar a tela neste sistema ({type(exc).__name__}).") from exc
    image = image.convert("RGB")
    scale = min(1.0, max_side / max(image.size))
    if scale < 1.0:
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
