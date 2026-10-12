"""Executa um pedido por vez, em segundo plano, sempre cancelável.

A interface nunca fica travada: o pedido roda em uma thread e publica
eventos (estado, progresso, mensagens). Se houver um pedido em andamento,
um novo é recusado com uma mensagem clara.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable

from ls_assistant.ai.assistant import Assistant
from ls_assistant.ai.base import ImageInput
from ls_assistant.errors import LSError
from ls_assistant.events import EventBus
from ls_assistant.security import CancelToken, EmergencyStop

log = logging.getLogger(__name__)

SpeakFn = Callable[[str], None]


class BusyError(LSError):
    """Já existe um pedido em andamento."""


class TaskRunner:
    def __init__(self, assistant: Assistant, emergency: EmergencyStop, events: EventBus) -> None:
        self._assistant = assistant
        self._emergency = emergency
        self._events = events
        self._lock = threading.Lock()
        self._token: CancelToken | None = None
        self._task_id: str | None = None

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._token is not None

    @property
    def current_task_id(self) -> str | None:
        with self._lock:
            return self._task_id

    def submit(
        self,
        text: str,
        *,
        images: list[ImageInput] | None = None,
        speak: SpeakFn | None = None,
        source: str = "texto",
    ) -> str:
        if self._emergency.active:
            raise LSError("A parada de emergência está ativa. Libere-a antes de pedir algo novo.")
        with self._lock:
            if self._token is not None:
                raise BusyError("Ainda estou terminando o pedido anterior. Você pode cancelá-lo se quiser.")
            token = self._emergency.new_token()
            task_id = uuid.uuid4().hex[:8]
            self._token = token
            self._task_id = task_id

        self._events.emit("message", {"role": "usuario", "text": text, "source": source})
        self._events.emit("task", {"id": task_id, "phase": "start", "texto": text[:160]})
        self._events.emit("state", {"state": "processing"})
        thread = threading.Thread(
            target=self._run, args=(task_id, text, images or [], token, speak),
            name=f"ls-task-{task_id}", daemon=True,
        )
        thread.start()
        return task_id

    def cancel_current(self, reason: str = "cancelado pelo usuário") -> bool:
        with self._lock:
            token = self._token
        if token is None:
            return False
        token.cancel(reason)
        return True

    def _run(self, task_id: str, text: str, images: list[ImageInput], token: CancelToken, speak: SpeakFn | None) -> None:
        try:
            reply = self._assistant.respond(text, images=images, cancel=token)
            self._events.emit("message", {"role": "ls", "text": reply.text, "mode": reply.mode,
                                          "actions": reply.actions, "model": reply.model})
            state = "cancelled" if reply.mode == "cancelado" else "done"
            self._events.emit("task", {"id": task_id, "phase": "end", "status": reply.mode})
            self._events.emit("state", {"state": state})
            if speak and reply.mode != "cancelado" and reply.text:
                speak(reply.text)
        except Exception:
            log.exception("Falha inesperada ao processar o pedido %s", task_id)
            self._events.emit("message", {"role": "sistema", "text": "Ocorreu um erro inesperado ao processar o pedido. Veja o registro de logs."})
            self._events.emit("task", {"id": task_id, "phase": "end", "status": "erro"})
            self._events.emit("state", {"state": "error"})
        finally:
            with self._lock:
                self._token = None
                self._task_id = None
