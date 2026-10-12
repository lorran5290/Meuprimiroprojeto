"""Janela nativa (pywebview, WebView2 no Windows) com minimizar para a bandeja.

- Minimizar a janela a esconde na bandeja; o núcleo continua rodando (inclusive a escuta).
- Fechar a janela encerra o LS. Para só esconder, use o ícone da bandeja.
- Fullscreen e controle de intensidade dos efeitos ficam na própria interface.
"""

from __future__ import annotations

import logging
from typing import Any

from ls_assistant.context import AppContext
from ls_assistant.errors import LSError

log = logging.getLogger(__name__)


def run_window(ctx: AppContext, url: str, *, start_hidden: bool = False) -> None:
    try:
        import webview
    except ImportError as exc:
        raise LSError("Janela nativa requer pywebview. Rode: pip install -r requirements.txt") from exc

    from ls_assistant.ui.tray import TrayIcon

    window = webview.create_window(
        "LS — Assistente",
        url,
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#050a14",
        hidden=start_hidden,
    )
    tray = TrayIcon.start(
        on_show=lambda: _show(window),
        on_toggle_mic=lambda: ctx.voice.set_microphone(not ctx.voice.mic_on),
        on_emergency=lambda: ctx.emergency.trigger("parada pela bandeja"),
        on_quit=lambda: window.destroy(),
    )
    if start_hidden and not tray.available:
        log.info("Bandeja indisponível: abrindo a janela mesmo com --autostart")
        window.show()

    def on_minimized(*_args: Any) -> None:
        if tray.available:
            window.hide()

    try:
        window.events.minimized += on_minimized
    except AttributeError:  # versões antigas do pywebview
        log.debug("Evento de minimizar indisponível nesta versão do pywebview")

    webview.start(debug=False)
    tray.stop()


def _show(window: Any) -> None:
    try:
        window.show()
        window.restore()
    except Exception:  # janela já destruída
        log.debug("Não foi possível mostrar a janela", exc_info=True)
