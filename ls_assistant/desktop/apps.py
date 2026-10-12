"""Localizar e abrir aplicativos, com verificação de que a abertura deu certo.

- Procura atalhos do Menu Iniciar (.lnk) e aliases comuns em português.
- Abrir: ``os.startfile`` no Windows, ``Popen`` para executáveis conhecidos.
- Verificação: o processo esperado precisa aparecer (ou manter-se vivo).
  Se não for possível confirmar, o resultado é "não verificado" — nunca "sucesso" presumido.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from ls_assistant.errors import LSError
from ls_assistant.memory.store import normalize

# Aliases: nome falado -> executável do Windows
ALIASES: dict[str, str] = {
    "bloco de notas": "notepad.exe",
    "notepad": "notepad.exe",
    "calculadora": "calc.exe",
    "paint": "mspaint.exe",
    "explorador de arquivos": "explorer.exe",
    "explorador": "explorer.exe",
    "gerenciador de tarefas": "taskmgr.exe",
    "prompt de comando": "cmd.exe",
    "powershell": "powershell.exe",
}
BROWSER_ALIASES = frozenset({"navegador", "browser", "chrome", "edge", "firefox"})
SETTINGS_ALIASES = frozenset({"configuracoes", "configurações", "configuracoes do windows"})

START_MENU_DIRS = (
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
)


@dataclass(frozen=True)
class AppEntry:
    name: str
    path: str


class AppCatalog:
    def __init__(self, start_menu_dirs: Iterable[Path] = START_MENU_DIRS) -> None:
        self._dirs = [d for d in start_menu_dirs if str(d) not in {"", "."}]
        self._entries: list[AppEntry] | None = None

    def scan(self) -> list[AppEntry]:
        if self._entries is None:
            found: dict[str, AppEntry] = {}
            for base in self._dirs:
                if not base.is_dir():
                    continue
                for dirpath, _dirs, files in os.walk(base):
                    for name in files:
                        if name.lower().endswith(".lnk"):
                            display = name[:-4]
                            found.setdefault(normalize(display), AppEntry(display, str(Path(dirpath) / name)))
            self._entries = sorted(found.values(), key=lambda e: e.name.lower())
        return self._entries

    def find(self, term: str, limit: int = 8) -> list[AppEntry]:
        needle = normalize(term)
        if not needle:
            return []
        entries = self.scan()
        names = {normalize(e.name): e for e in entries}
        scored: list[tuple[float, AppEntry]] = []
        for norm_name, entry in names.items():
            if needle == norm_name:
                score = 1.0
            elif needle in norm_name:
                score = 0.9
            else:
                score = difflib.SequenceMatcher(None, needle, norm_name).ratio()
            if score >= 0.6:
                scored.append((score, entry))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [e for _, e in scored[:limit]]


class AppLauncher:
    """Abre aplicativos e verifica o resultado. Recebe dependências para facilitar testes."""

    def __init__(
        self,
        catalog: AppCatalog,
        *,
        startfile: Callable[[str], None] | None = None,
        popen: Callable[[list[str]], Any] | None = None,
        process_names: Callable[[], set[str]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        verify_timeout_s: float = 6.0,
    ) -> None:
        self._catalog = catalog
        self._startfile = startfile or getattr(os, "startfile", None)
        self._popen = popen or (lambda args: subprocess.Popen(args, close_fds=True))
        self._process_names = process_names or _running_process_names
        self._sleep = sleep
        self._verify_timeout = verify_timeout_s

    def open(self, term: str) -> dict[str, Any]:
        needle = normalize(term)
        if not needle:
            raise LSError("Informe o nome do aplicativo.")
        if needle in {normalize(a) for a in BROWSER_ALIASES}:
            return {"status": "pedido_enviado", "aplicativo": "navegador padrão",
                    "detalhe": "Abrir o navegador padrão é feito com 'abrir_site'."}
        alias_exe = next((exe for name, exe in ALIASES.items() if normalize(name) == needle), None)
        if alias_exe:
            return self._launch_exe(term, alias_exe)

        matches = self._catalog.find(term)
        if not matches:
            raise LSError(f"Não encontrei nenhum aplicativo chamado '{term}' no Menu Iniciar.")
        exact = [m for m in matches if normalize(m.name) == needle]
        if len(exact) == 1:
            return self._launch_shortcut(exact[0])
        if len(matches) > 1:
            options = ", ".join(m.name for m in matches[:4])
            raise LSError(f"Encontrei vários possíveis aplicativos: {options}. Qual deles você quer abrir?")
        return self._launch_shortcut(matches[0])

    def _launch_exe(self, label: str, exe: str) -> dict[str, Any]:
        before = self._process_names()
        proc = self._popen([exe])
        pid = getattr(proc, "pid", None)
        deadline = time.monotonic() + self._verify_timeout
        while time.monotonic() < deadline:
            if pid is not None and _pid_alive(pid):
                return {"status": "verificado", "aplicativo": label, "pid": pid}
            self._sleep(0.3)
        if pid is None and exe.lower() in self._process_names() - before:
            return {"status": "verificado", "aplicativo": label}
        return {"status": "nao_verificado", "aplicativo": label,
                "detalhe": "Enviei o pedido, mas o processo não permaneceu em execução."}

    def _launch_shortcut(self, entry: AppEntry) -> dict[str, Any]:
        if self._startfile is None:
            raise LSError("Abrir atalhos só é suportado no Windows.")
        expected = normalize(entry.name)
        before = {normalize(n) for n in self._process_names()}
        self._startfile(entry.path)
        deadline = time.monotonic() + self._verify_timeout
        while time.monotonic() < deadline:
            current = {normalize(n) for n in self._process_names()}
            if current - before and any(expected.split(" ")[0] in n for n in current - before):
                return {"status": "verificado", "aplicativo": entry.name}
            self._sleep(0.4)
        return {"status": "nao_verificado", "aplicativo": entry.name,
                "detalhe": "Enviei o pedido ao Windows, mas não consegui confirmar que o aplicativo abriu."}


def _pid_alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).is_running()
    except psutil.Error:
        return False


def _running_process_names() -> set[str]:
    names: set[str] = set()
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name")
            if name:
                names.add(name.lower())
        except psutil.Error:
            continue
    return names
