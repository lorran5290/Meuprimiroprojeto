"""Montagem do LS e ponto de entrada.

Ordem de inicialização: configuração -> logs -> memória (+ dados iniciais) ->
auditoria -> segurança -> ferramentas -> IA -> voz -> servidor local -> janela.
Encerramento: voz e fala param, tarefas são canceladas, banco de dados é fechado.
"""

from __future__ import annotations

import argparse
import logging
import secrets
import socket
import sys
import threading
import time
from typing import Any

from ls_assistant import __version__
from ls_assistant.ai.assistant import Assistant
from ls_assistant.ai.conversation import Conversation
from ls_assistant.ai.gemini import GeminiProvider
from ls_assistant.automation.runner import TaskRunner
from ls_assistant.config import Settings, load_settings
from ls_assistant.context import AppContext
from ls_assistant.desktop.apps import AppCatalog, AppLauncher
from ls_assistant.desktop.files import FileService, PlanStore
from ls_assistant.desktop.windows import WindowManager, default_backend
from ls_assistant.errors import ConfigError, LSError
from ls_assistant.events import EventBus
from ls_assistant.logging_setup import configure_logging
from ls_assistant.memory.seed import apply_seed_memories
from ls_assistant.memory.store import MemoryStore
from ls_assistant.security import AuditLog, ConfirmationBroker, EmergencyStop, PathPolicy
from ls_assistant.settings.service import SettingsService
from ls_assistant.tools.builtin import ToolServices, build_registry
from ls_assistant.tools.executor import ToolExecutor
from ls_assistant.voice.controller import VoiceController
from ls_assistant.voice.tts import build_tts

log = logging.getLogger("ls")


def build_context(settings: Settings) -> AppContext:
    events = EventBus()
    memory = MemoryStore(settings.memory_db)
    created = apply_seed_memories(memory)
    if created:
        log.info("Memória inicial criada: %s itens editáveis", created)
    audit = AuditLog(settings.audit_db)
    broker = ConfirmationBroker(default_timeout_s=settings.confirmation_timeout_s, emit=events.emit)
    emergency = EmergencyStop(broker)
    paths = PathPolicy(settings.allowed_roots)
    plans = PlanStore(settings.plans_dir)
    files = FileService(paths, plans, settings.quarantine_dir)
    catalog = AppCatalog()
    apps = AppLauncher(catalog)
    backend = default_backend()
    windows = WindowManager(backend) if backend is not None else None

    provider = None
    if settings.gemini_api_key:
        provider = GeminiProvider(
            settings.gemini_api_key,
            settings.gemini_model,
            fallback_models=settings.gemini_fallback_models,
            timeout_s=settings.gemini_timeout_s,
        )
    else:
        log.warning("GEMINI_API_KEY não configurada: o LS funciona em modo local (sem conversa com a IA).")

    services = ToolServices(memory=memory, files=files, apps=apps, catalog=catalog,
                            windows=windows, provider=provider)
    registry = build_registry(services)
    executor = ToolExecutor(
        registry, audit=audit, broker=broker, emergency=emergency, events=events,
        default_timeout_s=settings.tool_timeout_s,
    )
    assistant = Assistant(
        provider=provider,
        executor=executor,
        memory=memory,
        conversation=Conversation(),
        events=events,
        keep_history=settings.keep_history,
        ai_unavailable_reason="a variável GEMINI_API_KEY não está configurada no arquivo .env",
    )
    runner = TaskRunner(assistant, emergency, events)
    tts = build_tts(settings.tts_enabled, voice=settings.tts_voice, rate=settings.tts_rate, volume=settings.tts_volume)

    def voice_command(text: str) -> None:
        speak = (lambda reply: voice.speak(reply)) if settings.tts_enabled and tts.available else None
        try:
            runner.submit(text, speak=speak, source="voz")
        except LSError as exc:
            events.emit("message", {"role": "sistema", "text": str(exc)})

    voice = VoiceController(
        tts=tts, events=events, on_command=voice_command,
        wake_words=settings.wake_words, vosk_model_path=settings.vosk_model_path,
        mic_device=settings.mic_device, wake_word_enabled=settings.wake_word_enabled,
    )
    emergency.add_hook(voice.interrupt_speech)

    ctx = AppContext(
        settings=settings, events=events, memory=memory, audit=audit, broker=broker, emergency=emergency,
        paths=paths, files=files, plans=plans, apps=apps, catalog=catalog, windows=windows, provider=provider,
        registry=registry, executor=executor, assistant=assistant, runner=runner, voice=voice, tts=tts,
        settings_service=SettingsService(settings, settings.settings_file),
    )
    return ctx


def _free_port(host: str, preferred: int) -> int:
    if preferred:
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _start_server(ctx: AppContext, token: str, port: int) -> tuple[Any, threading.Thread]:
    import uvicorn

    from ls_assistant.ui.server import create_app

    app = create_app(ctx, token)
    config = uvicorn.Config(app, host=ctx.settings.server_host, port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="ls-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise LSError("O servidor local não iniciou. Verifique se a porta escolhida está livre.")
    return server, thread


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ls", description="LS — assistente pessoal")
    parser.add_argument("--no-window", action="store_true", help="só o servidor local (abra a URL no navegador)")
    parser.add_argument("--autostart", action="store_true", help="inicia minimizado na bandeja (usado pelo Windows)")
    parser.add_argument("--version", action="version", version=f"LS {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    configure_logging(settings.log_level, settings.logs_dir, settings.secret_values())
    log.info("Iniciando LS %s (modelo: %s, dados: %s)", __version__, settings.gemini_model, settings.data_dir)
    if settings.gemini_api_key is None:
        log.warning("Sem GEMINI_API_KEY: conversa com a IA indisponível; funções locais continuam ativas.")

    ctx = build_context(settings)
    token = secrets.token_urlsafe(24)
    port = _free_port(settings.server_host, settings.server_port)
    server, thread = _start_server(ctx, token, port)
    url = f"http://{settings.server_host}:{port}/#t={token}"
    log.info("Interface local em http://%s:%s/", settings.server_host, port)

    try:
        if args.no_window:
            print(f"LS está rodando. Abra no navegador: {url}\nPressione Ctrl+C para encerrar.")
            while True:
                time.sleep(1)
        else:
            from ls_assistant.ui.window import run_window

            run_window(ctx, url, start_hidden=args.autostart)
    except KeyboardInterrupt:
        pass
    except LSError as exc:
        print(f"Não foi possível abrir a janela: {exc}", file=sys.stderr)
        log.error("Janela indisponível: %s", exc)
        return 1
    except Exception as exc:  # ex.: WebView2 ausente; o servidor pode continuar sem janela
        log.exception("Falha na janela nativa")
        print(
            f"Não consegui abrir a janela ({type(exc).__name__}). Verifique o WebView2 (README, seção 2)\n"
            f"ou rode: scripts\\iniciar_ls.bat --no-window e abra a URL acima no navegador.",
            file=sys.stderr,
        )
        return 1
    finally:
        log.info("Encerrando LS")
        ctx.shutdown()
        server.should_exit = True
        thread.join(timeout=5)
    return 0


