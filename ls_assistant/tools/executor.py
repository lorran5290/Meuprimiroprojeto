"""Executor de ferramentas: onde a decisão de segurança acontece.

Fluxo de cada chamada:
1. Ferramenta existe? Argumentos válidos (Pydantic)?
2. Parada de emergência ou cancelamento ativo? -> cancelada.
3. Política de risco: BLOCKED -> negada; CONFIRM/EXTERNAL -> pede aprovação.
4. Executa em thread separada com limite de tempo.
5. Registra auditoria e publica eventos. Erros viram status, nunca exceções para o modelo.

Cancelamento é cooperativo: uma função já em andamento no sistema pode terminar,
mas o LS não reporta sucesso enquanto o resultado não voltar.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from pydantic import ValidationError

from ls_assistant.errors import ActionCancelled, ActionDenied, AIUnavailableError, LSError
from ls_assistant.events import EventBus
from ls_assistant.security import AuditLog, CancelToken, ConfirmationBroker, EmergencyStop, decide
from ls_assistant.tools.base import ActionResult, ToolContext, ToolOutcome, ToolSpec, ToolUnavailable, ToolUnverified
from ls_assistant.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


def _friendly_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        field = ".".join(str(p) for p in err.get("loc", ())) or "argumento"
        parts.append(f"{field}: {err.get('msg', 'valor inválido')}")
    return "Argumentos inválidos — " + "; ".join(parts)


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        audit: AuditLog,
        broker: ConfirmationBroker,
        emergency: EmergencyStop,
        events: EventBus,
        default_timeout_s: float = 30.0,
        max_workers: int = 4,
    ) -> None:
        self._registry = registry
        self._audit = audit
        self._broker = broker
        self._emergency = emergency
        self._events = events
        self._default_timeout = default_timeout_s
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ls-tool")

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def declarations(self):  # noqa: ANN201 - tipo definido em ai.base
        return self._registry.declarations()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def execute(
        self,
        name: str,
        raw_args: dict[str, Any] | None = None,
        *,
        source: str = "assistente",
        cancel: CancelToken | None = None,
    ) -> ToolOutcome:
        started = time.monotonic()
        spec = self._registry.get(name)
        if spec is None:
            return self._finish(
                ToolOutcome(tool=name, status="unknown_tool", message=f"Ferramenta '{name}' não existe."),
                raw_args, source, started,
            )

        base = ToolOutcome(tool=name, status="ok", message="", risk=spec.risk.value)
        self._events.emit("tool", {"phase": "start", "tool": name, "title": spec.title, "risk": spec.risk.value})

        try:
            args = spec.args_model.model_validate(raw_args or {})
        except ValidationError as exc:
            base.status, base.message = "invalid_args", _friendly_validation_error(exc)
            return self._finish(base, raw_args, source, started)

        token = cancel or CancelToken()
        if self._emergency.active or token.cancelled:
            base.status, base.message = "cancelled", "Ação cancelada pela parada de emergência."
            return self._finish(base, raw_args, source, started)

        decision = decide(spec.risk)
        if decision == "deny":
            base.status, base.message = "denied", "Esta ação não é permitida pelo assistente."
            return self._finish(base, raw_args, source, started)

        if decision == "ask":
            outcome = self._ask_approval(spec, args, token, base)
            if outcome is not None:
                return self._finish(outcome, raw_args, source, started)

        return self._finish(self._run(spec, args, token, base), raw_args, source, started)

    # Internos ----------------------------------------------------------------
    def _ask_approval(self, spec: ToolSpec, args: Any, token: CancelToken, base: ToolOutcome) -> ToolOutcome | None:
        description = spec.describe(args) if spec.describe else spec.title
        request = self._broker.request(
            title=spec.title,
            description=description,
            risk=spec.risk.value,
            details=args.model_dump(mode="json"),
        )
        approved = self._broker.wait(request, token)
        if approved:
            base.approval = "aprovado"
            return None
        base.approval = request.reason or "recusado"
        base.status = "cancelled" if token.cancelled or "parada" in request.reason else "denied"
        base.message = (
            "Ação cancelada antes da aprovação."
            if base.status == "cancelled"
            else f"Ação não aprovada ({request.reason}). Nada foi alterado."
        )
        return base

    def _run(self, spec: ToolSpec, args: Any, token: CancelToken, base: ToolOutcome) -> ToolOutcome:
        ctx = ToolContext(cancel=token)
        future = self._pool.submit(self._invoke, spec, args, ctx)
        timeout = spec.timeout_s or self._default_timeout
        try:
            result = future.result(timeout=timeout)
        except FutureTimeout:
            token.cancel("tempo limite excedido")
            base.status = "timeout"
            base.message = f"A ação excedeu o limite de {int(timeout)} s e foi interrompida."
            return base
        except ActionCancelled as exc:
            base.status, base.message = "cancelled", str(exc) or "Ação cancelada."
            return base
        except ActionDenied as exc:
            base.status, base.message = "denied", str(exc)
            return base
        except (ToolUnavailable, AIUnavailableError) as exc:
            base.status, base.message = "unavailable", str(exc)
            return base
        except ToolUnverified as exc:
            base.status, base.message = "unverified", str(exc)
            return base
        except LSError as exc:
            base.status, base.message = "failed", str(exc)
            return base
        except Exception:  # erro inesperado: registra no log, não expõe detalhes ao modelo
            log.exception("Erro interno na ferramenta %s", spec.name)
            base.status, base.message = "failed", f"Erro interno ao executar '{spec.title}'. Veja o registro de logs."
            return base

        base.message = result.message
        base.data = result.data
        base.images = result.images
        return base

    @staticmethod
    def _invoke(spec: ToolSpec, args: Any, ctx: ToolContext) -> ActionResult:
        result = spec.handler(args, ctx)
        if not isinstance(result, ActionResult):
            raise LSError("A ferramenta devolveu um resultado em formato inválido.")
        return result

    def _finish(self, outcome: ToolOutcome, raw_args: dict[str, Any] | None, source: str, started: float) -> ToolOutcome:
        outcome.duration_ms = int((time.monotonic() - started) * 1000)
        if not outcome.message:
            outcome.message = "Concluído." if outcome.ok else "Sem detalhes."
        self._audit.record(
            tool=outcome.tool,
            risk=outcome.risk or "desconhecido",
            status=outcome.status,
            args=raw_args or {},
            message=outcome.message,
            source=source,
            approval=outcome.approval,
        )
        self._events.emit("tool", {"phase": "end", **outcome.to_event()})
        return outcome
