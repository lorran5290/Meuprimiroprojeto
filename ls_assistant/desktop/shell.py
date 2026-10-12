"""Navegador e área de transferência.

Limite honesto: abrir um site ou uma pesquisa no navegador confirma apenas que
o pedido foi enviado ao sistema. O LS não lê a página aberta por aqui; para
pesquisar e resumir resultados, use ``pesquisar_na_web`` (com fontes citadas).
"""

from __future__ import annotations

import re
import subprocess
import sys
import urllib.parse
import webbrowser
from typing import Any

from ls_assistant.errors import LSError

_ALLOWED_SCHEMES = frozenset({"http", "https"})


_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9-]+\.)+[a-z]{2,63}$", re.IGNORECASE)


def normalize_url(raw: str) -> str:
    """Aceita 'https://...' ou um domínio simples ('exemplo.com.br'). Nada além de http/https."""
    url = raw.strip()
    if not url:
        raise LSError("Informe o endereço do site.")
    if re.match(r"^[a-z][a-z0-9+.\-]*:", url, re.IGNORECASE) and not url.lower().startswith(("http://", "https://")):
        raise LSError("Só abro endereços http ou https.")  # ex.: javascript:, file:, mailto:
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise LSError("Endereço inválido. Exemplo: exemplo.com.br")
    if parsed.hostname != "localhost" and not _HOST_RE.match(parsed.hostname):
        raise LSError("Endereço inválido. Exemplo: exemplo.com.br")
    return url


def search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query.strip())


def open_url(raw: str) -> dict[str, Any]:
    url = normalize_url(raw)
    try:
        opened = webbrowser.open_new_tab(url)
    except webbrowser.Error as exc:
        raise LSError(f"Não consegui abrir o navegador: {exc}") from exc
    if not opened:
        return {"status": "nao_verificado", "url": url,
                "detalhe": "O sistema não confirmou a abertura do navegador."}
    return {"status": "pedido_enviado", "url": url,
            "detalhe": "Pedido enviado ao navegador padrão. Não consigo ver a página a partir daqui."}


def copy_to_clipboard(text: str) -> dict[str, Any]:
    if not text:
        raise LSError("Não há texto para copiar.")
    if sys.platform != "win32":
        raise LSError("Área de transferência só é suportada no Windows.")
    # clip.exe lê UTF-16LE, o que preserva acentos.
    completed = subprocess.run(["clip"], input=text.encode("utf-16-le"), check=False, capture_output=True)
    if completed.returncode != 0:
        raise LSError("O Windows recusou a cópia para a área de transferência.")
    return {"status": "verificado", "caracteres": len(text)}
