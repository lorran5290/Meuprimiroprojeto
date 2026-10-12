"""Ícone na bandeja do sistema (pystray, opcional).

Se o pacote não estiver instalado ou o sistema não suportar bandeja, ``available``
é False e a janela continua funcionando normalmente.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)


class TrayIcon:
    def __init__(self, icon: object | None) -> None:
        self._icon = icon

    @property
    def available(self) -> bool:
        return self._icon is not None

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()  # type: ignore[attr-defined]
            except Exception:
                log.debug("Bandeja já estava encerrada", exc_info=True)

    @classmethod
    def start(
        cls,
        *,
        on_show: Callable[[], None],
        on_toggle_mic: Callable[[], object],
        on_emergency: Callable[[], object],
        on_quit: Callable[[], None],
    ) -> TrayIcon:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            log.info("pystray/Pillow indisponíveis: sem ícone na bandeja")
            return cls(None)

        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((6, 6, size - 6, size - 6), outline=(56, 189, 248, 255), width=6)
        draw.ellipse((22, 22, size - 22, size - 22), fill=(56, 189, 248, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar LS", lambda *_: on_show(), default=True),
            pystray.MenuItem("Ligar/desligar microfone", lambda *_: on_toggle_mic()),
            pystray.MenuItem("Parada de emergência", lambda *_: on_emergency()),
            pystray.MenuItem("Sair", lambda *_: on_quit()),
        )
        icon = pystray.Icon("LS", image, "LS — Assistente", menu)
        threading.Thread(target=icon.run, name="ls-tray", daemon=True).start()
        return cls(icon)
