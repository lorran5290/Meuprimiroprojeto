"""Orquestrador da conversa: diálogo com o modelo + ferramentas + memória.

Laço de cada pedido:
1. Monta o contexto com memórias autorizadas relevantes.
2. Pede ao modelo a próxima resposta (texto e/ou chamadas de ferramenta).
3. Cada chamada passa pelo executor (que decide segurança e registra auditoria).
4. Os resultados voltam ao modelo, que responde ao usuário com base neles.

Se o serviço de IA estiver indisponível, o LS informa o motivo e executa,
quando possível, uma das funções locais (memória, sistema, abrir aplicativo).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from ls_assistant.ai.base import AIProvider, ImageInput, ToolCall, ToolResult, Turn
from ls_assistant.ai.conversation import Conversation
from ls_assistant.ai.prompts import build_system_prompt
from ls_assistant.errors import ActionCancelled, AIUnavailableError
from ls_assistant.events import EventBus
from ls_assistant.memory.store import MemoryStore
from ls_assistant.security import CancelToken
from ls_assistant.tools.base import ToolOutcome
from ls_assistant.tools.executor import ToolExecutor

log = logging.getLogger(__name__)


@dataclass
class AssistantReply:
    text: str
    mode: str = "ia"  # ia | local | cancelado | limite
    model: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)


class Assistant:
    def __init__(
        self,
        *,
        provider: AIProvider | None,
        executor: ToolExecutor,
        memory: MemoryStore,
        conversation: Conversation,
        events: EventBus,
        max_steps: int = 8,
        keep_history: bool = True,
        ai_unavailable_reason: str = "a variável GEMINI_API_KEY não está configurada no arquivo .env",
    ) -> None:
        self._provider = provider
        self._executor = executor
        self._memory = memory
        self._conversation = conversation
        self._events = events
        self._max_steps = max_steps
        self._keep_history = keep_history
        self._ai_reason = ai_unavailable_reason

    @property
    def ai_enabled(self) -> bool:
        return self._provider is not None

    def respond(self, text: str, *, images: list[ImageInput] | None = None, cancel: CancelToken | None = None) -> AssistantReply:
        token = cancel or CancelToken()
        self._conversation.add(Turn(role="user", text=text, images=list(images or [])))
        actions: list[dict[str, Any]] = []
        try:
            reply = self._run(text, token, actions)
        except ActionCancelled:
            reply = AssistantReply(text="Tarefa cancelada. Nada mais foi executado.", mode="cancelado", actions=actions)
        if self._keep_history:
            self._memory.log_message("usuario", text)
            self._memory.log_message("ls", reply.text)
        return reply

    # Laço principal ------------------------------------------------------
    def _run(self, text: str, token: CancelToken, actions: list[dict[str, Any]]) -> AssistantReply:
        if self._provider is None:
            return self._local_reply(text, token, actions, reason=self._ai_reason)

        memory_lines = [
            f"[{m.category}] {m.key + ': ' if m.key else ''}{m.content}"
            for m in self._memory.recall(text, limit=5)
        ]
        system = build_system_prompt(memory_lines)
        tools = self._executor.declarations()

        for _step in range(self._max_steps):
            token.raise_if_cancelled()
            self._events.emit("state", {"state": "processing"})
            try:
                model_reply = self._provider.generate(system=system, turns=self._conversation.turns(), tools=tools)
            except AIUnavailableError as exc:
                log.warning("IA indisponível (%s)", exc.kind)
                return self._local_reply(text, token, actions, reason=str(exc))

            self._conversation.add(
                Turn(
                    role="model",
                    text=model_reply.text,
                    tool_calls=model_reply.tool_calls,
                    raw_parts=model_reply.raw_parts,
                )
            )
            if not model_reply.tool_calls:
                return AssistantReply(
                    text=model_reply.text or "Não tenho uma resposta para isso agora.",
                    mode="ia",
                    model=model_reply.model,
                    actions=actions,
                )

            results, attachments = self._run_tool_calls(model_reply.tool_calls, token, actions)
            self._conversation.add(Turn(role="tool", tool_results=results))
            if attachments:
                self._conversation.add(Turn(role="user", text="Imagem capturada pela ferramenta para análise.", images=attachments))

        return AssistantReply(
            text="Atingi o limite de etapas para este pedido. Diga o que você quer que eu faça a seguir.",
            mode="limite",
            actions=actions,
        )

    def _run_tool_calls(
        self, calls: list[ToolCall], token: CancelToken, actions: list[dict[str, Any]]
    ) -> tuple[list[ToolResult], list[ImageInput]]:
        results: list[ToolResult] = []
        attachments: list[ImageInput] = []
        for call in calls:
            token.raise_if_cancelled()
            self._events.emit("state", {"state": "executing", "tool": call.name})
            outcome = self._executor.execute(call.name, call.args, source="assistente", cancel=token)
            actions.append(outcome.to_event())
            results.append(ToolResult(name=call.name, response=outcome.to_model_dict(), call_id=call.call_id))
            attachments.extend(outcome.images)
        return results, attachments

    # Modo local (IA indisponível) ----------------------------------------------
    def _local_reply(self, text: str, token: CancelToken, actions: list[dict[str, Any]], *, reason: str) -> AssistantReply:
        normalized = _normalize_pt(text)
        outcome: ToolOutcome | None = None
        body = ""

        if re.search(r"\b(cpu|processador|bateria|disco|rede|computador|sistema|estado do)\b", normalized):
            outcome = self._executor.execute("status_do_sistema", {}, cancel=token)
        elif re.search(r"\bprojetos?\b", normalized) and not re.search(r"\bsobre\b", normalized):
            outcome = self._executor.execute("consultar_memoria", {"categoria": "projetos"}, cancel=token)
        elif re.search(r"\b(lembr\w*|memoria|sei sobre|o que voce sabe|projetos?)\b", normalized):
            outcome = self._executor.execute("consultar_memoria", {"consulta": text}, cancel=token)
        elif re.match(r"^(abr\w*|inici\w*)\s+", normalized):
            name = re.sub(r"^(abr\w*|inici\w*)\s+(o |a |os |as )?", "", normalized).strip(" .!?")
            outcome = self._executor.execute("abrir_aplicativo", {"nome": name}, cancel=token)

        if outcome is not None:
            actions.append(outcome.to_event())
            body = outcome.message
            if outcome.ok and outcome.data.get("itens"):
                body += "\n" + "\n".join(f"- {item['titulo']}: {item['conteudo']}" for item in outcome.data["itens"])
            elif outcome.ok and outcome.data.get("sistema"):
                body += "\n" + outcome.data["sistema"]

        reason = reason.rstrip(".")
        header = f"A IA não está disponível agora: {reason}."
        if body:
            return AssistantReply(text=f"{header}\nFiz isto localmente:\n{body}", mode="local", actions=actions)
        return AssistantReply(
            text=(
                f"{header}\nSem IA, ainda posso consultar sua memória, mostrar o estado do computador "
                "e abrir aplicativos. Para conversas completas, tente de novo em alguns instantes."
            ),
            mode="local",
            actions=actions,
        )


def _normalize_pt(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()
