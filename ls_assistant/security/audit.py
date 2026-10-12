"""Registro local de ações relevantes (auditoria).

Guarda o que foi pedido, quem pediu, o nível de risco, o resultado e a
decisão de aprovação. Argumentos sensíveis são mascarados antes de gravar.
O usuário pode consultar e apagar os registros pela interface.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = ("senha", "password", "token", "secret", "chave", "api_key", "apikey", "credencial")
_MAX_VALUE_CHARS = 300


def redact_args(args: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in args.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            clean[key] = "***"
            continue
        text = value if isinstance(value, (int, float, bool)) or value is None else str(value)
        if isinstance(text, str) and len(text) > _MAX_VALUE_CHARS:
            text = text[:_MAX_VALUE_CHARS] + "…"
        clean[key] = text
    return clean


class AuditLog:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    source TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    message TEXT NOT NULL,
                    approval TEXT NOT NULL DEFAULT ''
                )"""
            )

    def record(
        self,
        *,
        tool: str,
        risk: str,
        status: str,
        args: dict[str, Any],
        message: str,
        source: str = "assistente",
        approval: str = "",
    ) -> int:
        payload = json.dumps(redact_args(args), ensure_ascii=False)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO audit (ts, source, tool, risk, status, args_json, message, approval)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), source, tool, risk, status, payload, message[:500], approval),
            )
            return int(cur.lastrowid)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 1000)),)).fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "source": r["source"],
                "tool": r["tool"],
                "risk": r["risk"],
                "status": r["status"],
                "args": json.loads(r["args_json"]),
                "message": r["message"],
                "approval": r["approval"],
            }
            for r in rows
        ]

    def delete(self, entry_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM audit WHERE id = ?", (entry_id,))
            return cur.rowcount > 0

    def clear(self) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM audit")
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
