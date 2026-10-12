"""Fila de aprovações pendentes.

Quando uma ação exige confirmação, o executor chama ``request`` e fica
esperando ``wait``. A interface mostra o pedido e chama ``resolve``.
Sem resposta dentro do prazo, a ação é recusada automaticamente.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ls_assistant.security.cancel import CancelToken

EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass
class PendingConfirmation:
    id: str
    title: str
    description: str
    risk: str
    details: dict[str, Any]
    created_at: float
    expires_at: float
    approved: bool | None = None
    reason: str = ""
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "risk": self.risk,
            "details": self.details,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class ConfirmationBroker:
    def __init__(self, *, default_timeout_s: float = 120.0, emit: EmitFn | None = None) -> None:
        self._default_timeout = default_timeout_s
        self._emit = emit or (lambda _type, _payload: None)
        self._pending: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()

    def request(
        self,
        *,
        title: str,
        description: str,
        risk: str,
        details: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> PendingConfirmation:
        now = time.time()
        req = PendingConfirmation(
            id=uuid.uuid4().hex[:12],
            title=title,
            description=description,
            risk=risk,
            details=details or {},
            created_at=now,
            expires_at=now + (timeout_s or self._default_timeout),
        )
        with self._lock:
            self._pending[req.id] = req
        self._emit("confirmation", {"action": "requested", **req.public()})
        return req

    def wait(self, req: PendingConfirmation, cancel: CancelToken | None = None) -> bool:
        """Bloqueia até decisão, expiração ou cancelamento. Retorna True só se aprovado."""
        try:
            while not req._event.is_set():
                if cancel is not None and cancel.cancelled:
                    self._finish(req, approved=False, reason="cancelado")
                    break
                if time.time() >= req.expires_at:
                    self._finish(req, approved=False, reason="tempo esgotado sem resposta")
                    break
                req._event.wait(0.2)
        finally:
            with self._lock:
                self._pending.pop(req.id, None)
        return bool(req.approved)

    def resolve(self, req_id: str, approved: bool) -> bool:
        with self._lock:
            req = self._pending.get(req_id)
        if req is None or req._event.is_set():
            return False
        self._finish(req, approved=approved, reason="aprovado" if approved else "recusado pelo usuário")
        return True

    def cancel_all(self, reason: str = "parada de emergência") -> int:
        with self._lock:
            reqs = list(self._pending.values())
        for req in reqs:
            self._finish(req, approved=False, reason=reason)
        return len(reqs)

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.public() for r in self._pending.values() if not r._event.is_set()]

    def _finish(self, req: PendingConfirmation, *, approved: bool, reason: str) -> None:
        if req._event.is_set():
            return
        req.approved = approved
        req.reason = reason
        req._event.set()
        self._emit("confirmation", {"action": "approved" if approved else "denied", "id": req.id, "reason": reason})
