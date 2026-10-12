"""Política de caminhos: o LS só toca em pastas do usuário autorizadas.

- Caminhos são resolvidos (links simbólicos incluídos) antes da checagem.
- Qualquer caminho dentro de áreas do sistema é recusado.
- Caminhos relativos são resolvidos a partir da primeira pasta permitida.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from ls_assistant.errors import PathNotAllowed

# Nomes (em minúsculas) de pastas do sistema e de credenciais que nunca são tocadas.
BLOCKED_PARTS = frozenset(
    {
        "windows",
        "system32",
        "program files",
        "program files (x86)",
        "programdata",
        "$recycle.bin",
        "system volume information",
        "appdata",
        ".ssh",
        ".gnupg",
    }
)


class PathPolicy:
    def __init__(self, roots: Iterable[Path]) -> None:
        resolved = [Path(os.path.abspath(Path(r).expanduser())) for r in roots]
        if not resolved:
            raise ValueError("É preciso configurar pelo menos uma pasta permitida.")
        self.roots: tuple[Path, ...] = tuple(resolved)

    @property
    def default_root(self) -> Path:
        return self.roots[0]

    def check(self, raw: str | Path, *, must_exist: bool = False) -> Path:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self.default_root / candidate
        resolved = Path(os.path.realpath(candidate))

        if any(part.lower() in BLOCKED_PARTS for part in resolved.parts):
            raise PathNotAllowed(f"Caminho protegido pelo sistema: {resolved.name or resolved}")
        if not self.is_inside_roots(resolved):
            raise PathNotAllowed(
                f"'{resolved}' está fora das pastas permitidas. "
                "Peça para incluir a pasta em LS_ALLOWED_ROOTS, se for o caso."
            )
        if must_exist and not resolved.exists():
            raise PathNotAllowed(f"Não encontrei '{resolved}'.")
        return resolved

    def is_inside_roots(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.roots)

    def is_root(self, path: Path) -> bool:
        return any(path == root for root in self.roots)
