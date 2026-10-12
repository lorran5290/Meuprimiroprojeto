"""Serviços compartilhados montados uma vez pelo app e usados pela interface e pelo núcleo."""

from __future__ import annotations

from dataclasses import dataclass

from ls_assistant.ai.assistant import Assistant
from ls_assistant.ai.base import AIProvider
from ls_assistant.automation.runner import TaskRunner
from ls_assistant.config import Settings
from ls_assistant.desktop.apps import AppCatalog, AppLauncher
from ls_assistant.desktop.files import FileService, PlanStore
from ls_assistant.desktop.windows import WindowManager
from ls_assistant.events import EventBus
from ls_assistant.memory.store import MemoryStore
from ls_assistant.security import AuditLog, ConfirmationBroker, EmergencyStop, PathPolicy
from ls_assistant.settings.service import SettingsService
from ls_assistant.tools.executor import ToolExecutor
from ls_assistant.tools.registry import ToolRegistry
from ls_assistant.voice.controller import VoiceController
from ls_assistant.voice.tts import TTSEngine, WindowsSpeechTTS


@dataclass
class AppContext:
    settings: Settings
    events: EventBus
    memory: MemoryStore
    audit: AuditLog
    broker: ConfirmationBroker
    emergency: EmergencyStop
    paths: PathPolicy
    files: FileService
    plans: PlanStore
    apps: AppLauncher
    catalog: AppCatalog
    windows: WindowManager | None
    provider: AIProvider | None
    registry: ToolRegistry
    executor: ToolExecutor
    assistant: Assistant
    runner: TaskRunner
    voice: VoiceController
    tts: TTSEngine
    settings_service: SettingsService

    def apply_settings(self, new: Settings) -> None:
        """Aplica preferências alteradas pela interface, sem reiniciar o LS."""
        self.settings = new
        if isinstance(self.tts, WindowsSpeechTTS):
            self.tts.configure(voice=new.tts_voice, rate=new.tts_rate, volume=new.tts_volume)
        if self.provider is not None:
            self.provider.set_models(new.gemini_model, new.gemini_fallback_models)
        self.voice.set_wake_enabled(new.wake_word_enabled)

    def shutdown(self) -> None:
        """Encerra com segurança: cancela o que estiver em andamento e fecha os recursos."""
        self.runner.cancel_current("encerramento do LS")
        self.broker.cancel_all("encerramento do LS")
        self.voice.shutdown()
        self.executor.shutdown()
        self.memory.close()
        self.audit.close()
