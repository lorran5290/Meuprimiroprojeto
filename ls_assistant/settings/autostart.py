"""Iniciar com o Windows — só quando o usuário ativa explicitamente.

Usa a chave HKCU\\...\\Run (não exige administrador). Ao desativar, remove a entrada.
Fora do Windows, a função informa que não é suportada.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ls_assistant.errors import LSError

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LS Assistente"


def autostart_command(project_root: Path) -> str:
    """Comando usado no Run: o Python do ambiente virtual sem janela de console."""
    pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
    interpreter = str(pythonw) if pythonw.exists() else sys.executable
    return f'"{interpreter}" -m ls_assistant --autostart'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(enabled: bool, project_root: Path) -> bool:
    if sys.platform != "win32":
        raise LSError("Iniciar com o Windows só está disponível no Windows.")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, autostart_command(project_root))
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    return is_enabled()
