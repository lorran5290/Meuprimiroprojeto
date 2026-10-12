"""Servidor local da interface (FastAPI + WebSocket).

Segurança:
- Escuta só em 127.0.0.1 e aceita apenas os hosts localhost/127.0.0.1 (evita DNS rebinding).
- Toda rota /api e o WebSocket exigem um token aleatório gerado a cada execução.
- Nenhuma chave de API é enviada ao navegador.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from ls_assistant import __version__
from ls_assistant.automation.runner import BusyError
from ls_assistant.config import PROJECT_ROOT
from ls_assistant.context import AppContext
from ls_assistant.desktop import system_info
from ls_assistant.errors import LSError
from ls_assistant.memory.backup import export_backup, import_backup
from ls_assistant.memory.store import CATEGORIES, SecretRefused
from ls_assistant.settings import autostart

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ChatIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


class ConfirmIn(BaseModel):
    aprovado: bool


class MicIn(BaseModel):
    ligado: bool


class MemoriaIn(BaseModel):
    conteudo: str = Field(..., min_length=1, max_length=4000)
    categoria: str = "geral"
    chave: str = Field("", max_length=120)
    sensivel: bool = False


class MemoriaPatch(BaseModel):
    conteudo: str | None = Field(None, max_length=4000)
    categoria: str | None = None
    chave: str | None = Field(None, max_length=120)
    sensivel: bool | None = None


class ImportIn(BaseModel):
    caminho: str = Field(..., min_length=1)
    modo: str = "mesclar"


class ConfigPatch(BaseModel):
    valores: dict[str, Any]


def _error(exc: LSError, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


def create_app(ctx: AppContext, session_token: str) -> FastAPI:
    app = FastAPI(title="LS", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    # O Starlette compara só o nome do host (sem porta).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def require_token(x_ls_token: str = Header(default="")) -> None:
        if not secrets.compare_digest(x_ls_token, session_token):
            raise HTTPException(status_code=401, detail="Sessão inválida. Reabra o LS.")

    auth = [Depends(require_token)]

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # Estado ----------------------------------------------------------------
    @app.get("/api/status", dependencies=auth)
    def status() -> dict[str, Any]:
        return {
            "versao": __version__,
            "ia": {
                "ativa": ctx.assistant.ai_enabled,
                "modelo": ctx.settings.gemini_model if ctx.assistant.ai_enabled else None,
                "modelos_de_reserva": list(ctx.settings.gemini_fallback_models),
            },
            "ocupado": ctx.runner.busy,
            "emergencia": ctx.emergency.active,
            "voz": ctx.voice.status(),
            "pastas_permitidas": [str(p) for p in ctx.paths.roots],
            "janelas_disponiveis": ctx.windows is not None,
            "pastas_de_dados": str(ctx.settings.data_dir),
        }

    @app.get("/api/catalogo", dependencies=auth)
    def catalogo() -> list[dict[str, Any]]:
        return ctx.registry.catalog()

    @app.get("/api/eventos", dependencies=auth)
    def eventos(limite: int = Query(100, ge=1, le=300)) -> list[dict[str, Any]]:
        return ctx.events.recent(limite)

    @app.get("/api/sistema", dependencies=auth)
    def sistema() -> dict[str, Any]:
        return system_info.system_status()

    # Conversa e ações ---------------------------------------------------------
    @app.post("/api/chat", dependencies=auth, status_code=202)
    def chat(body: ChatIn) -> dict[str, str]:
        speak = None
        if ctx.settings.tts_enabled and ctx.tts.available:
            speak = lambda text: ctx.voice.speak(text)  # noqa: E731 - closure curta
        try:
            task_id = ctx.runner.submit(body.texto.strip(), speak=speak, source="texto")
        except BusyError as exc:
            raise _error(exc, 409) from exc
        except LSError as exc:
            raise _error(exc, 423) from exc
        return {"tarefa": task_id}

    @app.post("/api/cancelar", dependencies=auth)
    def cancelar() -> dict[str, bool]:
        return {"cancelado": ctx.runner.cancel_current()}

    @app.post("/api/emergencia", dependencies=auth)
    def emergencia() -> dict[str, Any]:
        result = ctx.emergency.trigger()
        ctx.voice.interrupt_speech()
        ctx.events.emit("state", {"state": "cancelled", "motivo": "parada de emergência"})
        return result

    @app.post("/api/emergencia/liberar", dependencies=auth)
    def liberar() -> dict[str, bool]:
        ctx.emergency.reset()
        ctx.events.emit("emergency", {"active": False})
        return {"ativa": False}

    @app.get("/api/confirmacoes", dependencies=auth)
    def confirmacoes() -> list[dict[str, Any]]:
        return ctx.broker.pending()

    @app.post("/api/confirmacoes/{req_id}", dependencies=auth)
    def confirmar(req_id: str, body: ConfirmIn) -> dict[str, bool]:
        if not ctx.broker.resolve(req_id, body.aprovado):
            raise HTTPException(status_code=404, detail="Esta confirmação não está mais pendente.")
        return {"aprovado": body.aprovado}

    # Voz ---------------------------------------------------------------------------
    @app.post("/api/microfone", dependencies=auth)
    def microfone(body: MicIn) -> dict[str, Any]:
        try:
            return ctx.voice.set_microphone(body.ligado)
        except LSError as exc:
            raise _error(exc, 422) from exc

    @app.post("/api/falar", dependencies=auth)
    def falar() -> dict[str, Any]:
        try:
            return ctx.voice.talk_once()
        except LSError as exc:
            raise _error(exc, 422) from exc

    @app.post("/api/fala/parar", dependencies=auth)
    def parar_fala() -> dict[str, bool]:
        return {"interrompida": ctx.voice.interrupt_speech()}

    @app.get("/api/vozes", dependencies=auth)
    def vozes() -> list[dict[str, str]]:
        return ctx.tts.list_voices()

    # Memória -------------------------------------------------------------------------
    @app.get("/api/memorias", dependencies=auth)
    def listar_memorias(consulta: str = "", categoria: str = "") -> list[dict[str, Any]]:
        if consulta.strip():
            found = ctx.memory.search(consulta, category=categoria or None, limit=100, include_sensitive=True)
        else:
            found = ctx.memory.list(category=categoria or None, limit=200)
        return [m.public(mask_sensitive=True) for m in found]

    @app.get("/api/memorias/categorias", dependencies=auth)
    def categorias() -> dict[str, str]:
        return CATEGORIES

    @app.get("/api/memorias/conflitos", dependencies=auth)
    def conflitos() -> list[dict[str, Any]]:
        return [{"chave": a.key, "versoes": [a.public(mask_sensitive=True), b.public(mask_sensitive=True)]}
                for a, b in ctx.memory.conflicts()]

    @app.post("/api/memorias", dependencies=auth, status_code=201)
    def criar_memoria(body: MemoriaIn) -> dict[str, Any]:
        try:
            result = ctx.memory.add(body.conteudo, category=body.categoria, key=body.chave, sensitive=body.sensivel,
                                    source="usuario")
        except (LSError, SecretRefused) as exc:
            raise _error(exc, 422) from exc
        return {"memoria": result.memory.public(mask_sensitive=True),
                "conflitos": [m.public(mask_sensitive=True) for m in result.conflicts]}

    @app.patch("/api/memorias/{memoria_id}", dependencies=auth)
    def editar_memoria(memoria_id: int, body: MemoriaPatch) -> dict[str, Any]:
        try:
            updated = ctx.memory.update(memoria_id, content=body.conteudo, key=body.chave,
                                        category=body.categoria, sensitive=body.sensivel)
        except (LSError, SecretRefused) as exc:
            raise _error(exc, 422) from exc
        return updated.public(mask_sensitive=True)

    @app.delete("/api/memorias/{memoria_id}", dependencies=auth)
    def apagar_memoria(memoria_id: int) -> dict[str, bool]:
        if not ctx.memory.delete(memoria_id):
            raise HTTPException(status_code=404, detail="Memória não encontrada.")
        ctx.audit.record(tool="apagar_memoria_manual", risk="confirmacao", status="ok",
                         args={"memoria_id": memoria_id}, message="Apagada pela interface", source="usuario")
        return {"apagada": True}

    @app.post("/api/memorias/backup", dependencies=auth)
    def backup() -> dict[str, Any]:
        target = ctx.settings.backups_dir / f"ls-memoria-{_stamp()}.json"
        return export_backup(ctx.memory, target)

    @app.post("/api/memorias/importar", dependencies=auth)
    def importar(body: ImportIn) -> dict[str, Any]:
        source = Path(body.caminho).expanduser().resolve()
        allowed = [ctx.settings.backups_dir.resolve(), *ctx.paths.roots]
        if not any(source == root or root in source.parents for root in allowed):
            raise HTTPException(status_code=422, detail="Importe apenas arquivos da pasta de backups do LS ou das pastas permitidas.")
        try:
            return import_backup(ctx.memory, source, mode=body.modo, backups_dir=ctx.settings.backups_dir)
        except LSError as exc:
            raise _error(exc, 422) from exc

    # Histórico e auditoria -----------------------------------------------------
    @app.get("/api/historico", dependencies=auth)
    def historico() -> list[dict[str, Any]]:
        return ctx.memory.recent_messages(200)

    @app.delete("/api/historico", dependencies=auth)
    def limpar_historico() -> dict[str, int]:
        return {"apagadas": ctx.memory.clear_history()}

    @app.get("/api/auditoria", dependencies=auth)
    def auditoria(limite: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
        return ctx.audit.list(limite)

    @app.delete("/api/auditoria/{entry_id}", dependencies=auth)
    def apagar_auditoria(entry_id: int) -> dict[str, bool]:
        return {"apagada": ctx.audit.delete(entry_id)}

    @app.delete("/api/auditoria", dependencies=auth)
    def limpar_auditoria() -> dict[str, int]:
        return {"apagadas": ctx.audit.clear()}

    # Configurações -----------------------------------------------------------------
    @app.get("/api/configuracoes", dependencies=auth)
    def configuracoes() -> dict[str, Any]:
        return ctx.settings_service.current.public_dict()

    @app.patch("/api/configuracoes", dependencies=auth)
    def alterar_configuracoes(body: ConfigPatch) -> dict[str, Any]:
        try:
            new = ctx.settings_service.update(body.valores)
            if "autostart" in body.valores:
                autostart.set_enabled(bool(body.valores["autostart"]), PROJECT_ROOT)
        except (LSError, OSError) as exc:
            raise _error(exc if isinstance(exc, LSError) else LSError(str(exc)), 422) from exc
        ctx.apply_settings(new)
        return new.public_dict()

    # Tempo real ----------------------------------------------------------------------
    @app.websocket("/ws")
    async def websocket(websocket: WebSocket, token: str = "") -> None:
        if not token or not secrets.compare_digest(token, session_token):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)

        def push(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(_offer, queue, event)

        unsubscribe = ctx.events.subscribe(push)
        try:
            await websocket.send_json({"type": "hello", "payload": {"versao": __version__}})
            for event in ctx.events.recent(100):
                await websocket.send_json(event)
            # Marca o fim do replay: só eventos depois daqui são "ao vivo" (ex.: abrem aprovações).
            await websocket.send_json({"type": "replay_end", "payload": {}})
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        except Exception:  # cliente sumiu no meio de um envio
            log.debug("WebSocket encerrado", exc_info=True)
        finally:
            unsubscribe()

    return app


def _offer(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # interface lenta: descarta o excedente em vez de acumular memória


def _stamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d-%H%M%S")
