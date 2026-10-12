"""Gerenciamento de janelas: listar, ativar, minimizar, maximizar, fechar.

A lógica (buscar por título, checar ambiguidade, verificar resultado) fica
em ``WindowManager`` e é testável com um backend falso. ``Win32Backend`` usa
as APIs nativas do Windows via ctypes e só funciona no Windows.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from ls_assistant.errors import LSError
from ls_assistant.memory.store import normalize

SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
WM_CLOSE = 0x0010


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    pid: int
    minimized: bool
    maximized: bool


class WindowBackend(Protocol):
    def list_windows(self) -> list[WindowInfo]: ...
    def show(self, handle: int, command: int) -> None: ...
    def activate(self, handle: int) -> bool: ...
    def close(self, handle: int) -> None: ...
    def is_hung(self, handle: int) -> bool: ...


class WindowManager:
    def __init__(self, backend: WindowBackend) -> None:
        self._backend = backend

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        windows = [w for w in self._backend.list_windows() if w.title.strip()]
        return [
            {"titulo": w.title, "pid": w.pid, "minimizada": w.minimized, "maximizada": w.maximized}
            for w in windows[: max(1, min(limit, 200))]
        ]

    def _find(self, fragment: str) -> WindowInfo:
        needle = normalize(fragment)
        if not needle:
            raise LSError("Informe parte do título da janela.")
        matches = [w for w in self._backend.list_windows() if needle in normalize(w.title)]
        if not matches:
            raise LSError(f"Não encontrei nenhuma janela com '{fragment}' no título.")
        exact = [w for w in matches if normalize(w.title) == needle]
        if len(matches) > 1 and len(exact) != 1:
            titles = "; ".join(w.title for w in matches[:5])
            raise LSError(f"Há mais de uma janela com esse nome: {titles}. Seja mais específico.")
        return exact[0] if exact else matches[0]

    def activate(self, fragment: str) -> dict[str, Any]:
        window = self._find(fragment)
        ok = self._backend.activate(window.handle)
        if not ok:
            return {"status": "nao_verificado", "janela": window.title,
                    "detalhe": "O Windows não permitiu trazer a janela para a frente."}
        return {"status": "verificado", "janela": window.title}

    def minimize(self, fragment: str) -> dict[str, Any]:
        return self._show(fragment, SW_MINIMIZE, "minimizada")

    def maximize(self, fragment: str) -> dict[str, Any]:
        return self._show(fragment, SW_MAXIMIZE, "maximizada")

    def _show(self, fragment: str, command: int, expected: str) -> dict[str, Any]:
        window = self._find(fragment)
        self._backend.show(window.handle, command)
        after = next((w for w in self._backend.list_windows() if w.handle == window.handle), None)
        if after is None:
            return {"status": "verificado", "janela": window.title, "estado": "fechada"}
        done = after.minimized if expected == "minimizada" else after.maximized
        if done:
            return {"status": "verificado", "janela": window.title, "estado": expected}
        return {"status": "nao_verificado", "janela": window.title,
                "detalhe": f"Pedi para deixar a janela {expected}, mas não consegui confirmar."}

    def close(self, fragment: str) -> dict[str, Any]:
        window = self._find(fragment)
        self._backend.close(window.handle)
        still = any(w.handle == window.handle for w in self._backend.list_windows())
        if still:
            return {"status": "nao_verificado", "janela": window.title,
                    "detalhe": "Enviei o pedido de fechamento; a janela continua aberta (pode estar pedindo para salvar)."}
        return {"status": "verificado", "janela": window.title}

    def is_responding(self, pid: int) -> dict[str, Any]:
        windows = [w for w in self._backend.list_windows() if w.pid == pid]
        if not windows:
            return {"status": "sem_janela", "detalhe": "O processo não tem janela visível; não é possível verificar."}
        hung = any(self._backend.is_hung(w.handle) for w in windows)
        return {"status": "nao_responde" if hung else "responde", "pid": pid, "janelas": len(windows)}


class Win32Backend:
    """Implementação nativa (user32). Só disponível no Windows."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise LSError("Controle de janelas só é suportado no Windows.")
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._wt = wintypes

    def list_windows(self) -> list[WindowInfo]:
        ct, user32, wt = self._ct, self._user32, self._wt
        results: list[WindowInfo] = []
        enum_proc_t = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ct.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ct.byref(pid))
            results.append(
                WindowInfo(
                    handle=hwnd,
                    title=buffer.value,
                    pid=int(pid.value),
                    minimized=bool(user32.IsIconic(hwnd)),
                    maximized=bool(user32.IsZoomed(hwnd)),
                )
            )
            return True

        user32.EnumWindows(enum_proc_t(callback), 0)
        return results

    def show(self, handle: int, command: int) -> None:
        self._user32.ShowWindow(handle, command)

    def activate(self, handle: int) -> bool:
        self._user32.ShowWindow(handle, SW_RESTORE)
        return bool(self._user32.SetForegroundWindow(handle))

    def close(self, handle: int) -> None:
        self._user32.PostMessageW(handle, WM_CLOSE, 0, 0)

    def is_hung(self, handle: int) -> bool:
        return bool(self._user32.IsHungAppWindow(handle))


def default_backend() -> WindowBackend | None:
    if os.name != "nt":
        return None
    return Win32Backend()
