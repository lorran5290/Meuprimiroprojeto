"""Configuração, política de risco, caminhos, confirmações, auditoria e parada de emergência."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from ls_assistant.config import load_settings
from ls_assistant.errors import ConfigError, PathNotAllowed
from ls_assistant.events import EventBus
from ls_assistant.logging_setup import SecretFilter
from ls_assistant.security import (
    AuditLog,
    CancelToken,
    ConfirmationBroker,
    EmergencyStop,
    PathPolicy,
    Risk,
    decide,
    redact_args,
)
from ls_assistant.settings.service import SettingsService

FAKE_GOOGLE_KEY = "AI" + "za" + "Fake" + "0" * 30  # formato apenas; não é chave real
FAKE_NEW_KEY = "AQ" + "." + "segredo" + "-" + "de-teste-123"  # formato apenas


# Configuração ---------------------------------------------------------------
def test_defaults_do_not_expose_key_and_use_verified_model(tmp_path: Path):
    s = load_settings({"LS_DATA_DIR": str(tmp_path)}, dotenv_path=None)
    assert s.gemini_api_key is None
    assert s.gemini_model == "gemini-3.5-flash"
    assert "gemini_api_key" not in s.public_dict()
    assert s.public_dict()["gemini_api_key_configured"] is False


def test_env_key_is_read_and_reported_only_as_configured(tmp_path: Path):
    s = load_settings({"LS_DATA_DIR": str(tmp_path), "GEMINI_API_KEY": FAKE_NEW_KEY}, dotenv_path=None)
    assert s.gemini_api_key == FAKE_NEW_KEY
    public = json.dumps(s.public_dict())
    assert "segredo-de-teste" not in public


def test_settings_json_is_overridden_by_environment(tmp_path: Path):
    (tmp_path / "settings.json").write_text(json.dumps({"tts_rate": 3, "gemini_model": "gemini-3.5-flash"}), encoding="utf-8")
    s = load_settings({"LS_DATA_DIR": str(tmp_path), "LS_TTS_RATE": "-2"}, dotenv_path=None)
    assert s.tts_rate == -2  # ambiente vence
    assert s.gemini_model == "gemini-3.5-flash"


def test_invalid_number_is_a_config_error(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_settings({"LS_DATA_DIR": str(tmp_path), "LS_TTS_RATE": "rápido"}, dotenv_path=None)


def test_volume_and_intensity_are_clamped(tmp_path: Path):
    s = load_settings({"LS_DATA_DIR": str(tmp_path), "LS_TTS_VOLUME": "500", "LS_EFFECTS_INTENSITY": "3"}, dotenv_path=None)
    assert s.tts_volume == 100
    assert s.effects_intensity == 1.0


def test_secret_filter_redacts_keys_in_logs():
    import logging

    flt = SecretFilter(["MINHA-CHAVE-LOCAL-XYZ"])
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "chave=%s e %s", ("MINHA-CHAVE-LOCAL-XYZ", FAKE_GOOGLE_KEY), None)
    flt.filter(record)
    text = record.getMessage()
    assert "MINHA-CHAVE" not in text and "AIza" not in text
    assert "[segredo-oculto]" in text


def test_settings_service_validates_and_persists(tmp_path: Path):
    s = load_settings({"LS_DATA_DIR": str(tmp_path)}, dotenv_path=None)
    service = SettingsService(s, s.settings_file)
    new = service.update({"tts_rate": 4, "effects_intensity": 0.5})
    assert new.tts_rate == 4
    stored = json.loads(s.settings_file.read_text(encoding="utf-8"))
    assert stored["tts_rate"] == 4
    from ls_assistant.errors import LSError

    with pytest.raises(LSError):
        service.update({"gemini_api_key": "x"})  # segredo nunca editável pela interface
    with pytest.raises(LSError):
        service.update({"tts_volume": 101})
    with pytest.raises(LSError):
        service.update({"gemini_model": "../../etc"})


# Política de risco ---------------------------------------------------------
def test_risk_decisions():
    assert decide(Risk.READ) == "auto"
    assert decide(Risk.REVERSIBLE) == "auto"
    assert decide(Risk.CONFIRM) == "ask"
    assert decide(Risk.EXTERNAL) == "ask"
    assert decide(Risk.BLOCKED) == "deny"


# Caminhos --------------------------------------------------------------------
def test_path_policy_allows_inside_and_refuses_outside(sandbox):
    policy = PathPolicy([sandbox["docs"]])
    inside = policy.check("relatorio.txt")
    assert inside == (sandbox["docs"] / "relatorio.txt").resolve()
    with pytest.raises(PathNotAllowed):
        policy.check(sandbox["root"] / "fora.txt")
    with pytest.raises(PathNotAllowed):
        policy.check("../../etc/passwd")


def test_path_policy_refuses_protected_system_locations(sandbox):
    policy = PathPolicy([sandbox["root"]])
    with pytest.raises(PathNotAllowed):
        policy.check(sandbox["root"] / "Windows" / "System32" / "x.dll")
    with pytest.raises(PathNotAllowed):
        policy.check(sandbox["root"] / "AppData" / "Roaming" / "x.txt")


def test_symlink_escape_is_refused(sandbox):
    target = sandbox["root"] / "secreto"
    target.mkdir()
    link = sandbox["docs"] / "atalho"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("sistema sem permissão para criar links simbólicos")
    policy = PathPolicy([sandbox["docs"]])
    with pytest.raises(PathNotAllowed):
        policy.check(link / "dado.txt")


# Confirmações ---------------------------------------------------------------
def test_confirmation_approved_from_another_thread():
    events = []
    broker = ConfirmationBroker(default_timeout_s=5, emit=lambda k, p: events.append((k, p)))
    req = broker.request(title="Apagar", description="teste", risk="confirmacao")
    threading.Timer(0.05, lambda: broker.resolve(req.id, True)).start()
    assert broker.wait(req) is True
    assert req.reason == "aprovado"
    assert broker.pending() == []


def test_confirmation_denied_and_timeout_mean_nothing_runs():
    broker = ConfirmationBroker(default_timeout_s=5)
    req = broker.request(title="x", description="y", risk="confirmacao")
    broker.resolve(req.id, False)
    assert broker.wait(req) is False

    slow = broker.request(title="x", description="y", risk="confirmacao", timeout_s=0.1)
    assert broker.wait(slow) is False
    assert "tempo esgotado" in slow.reason


def test_confirmation_cancelled_by_token():
    broker = ConfirmationBroker(default_timeout_s=30)
    token = CancelToken()
    req = broker.request(title="x", description="y", risk="externo")
    threading.Timer(0.05, lambda: token.cancel("cancelado")).start()
    started = time.monotonic()
    assert broker.wait(req, token) is False
    assert time.monotonic() - started < 5


# Parada de emergência ------------------------------------------------------------
def test_emergency_cancels_tasks_approvals_and_runs_hooks():
    broker = ConfirmationBroker(default_timeout_s=30)
    emergency = EmergencyStop(broker)
    hook_calls = []
    emergency.add_hook(lambda: hook_calls.append("fala-parada"))
    token = emergency.new_token()
    req = broker.request(title="x", description="y", risk="confirmacao")

    result = emergency.trigger()

    assert token.cancelled
    assert result == {"tasks_cancelled": 1, "approvals_denied": 1}
    assert hook_calls == ["fala-parada"]
    assert broker.wait(req) is False
    assert emergency.new_token().cancelled  # novas tarefas nascem canceladas até liberar
    emergency.reset()
    assert not emergency.active


# Auditoria --------------------------------------------------------------------------
def test_audit_redacts_sensitive_args_and_supports_delete(tmp_path: Path):
    audit = AuditLog(tmp_path / "audit.sqlite3")
    entry_id = audit.record(tool="abrir_site", risk="reversivel", status="ok",
                            args={"endereco": "exemplo.com", "api_token": "abc123", "senha": "x"}, message="ok")
    row = audit.list()[0]
    assert row["args"]["api_token"] == "***"
    assert row["args"]["senha"] == "***"
    assert row["args"]["endereco"] == "exemplo.com"
    assert audit.delete(entry_id) is True
    assert audit.list() == []
    audit.close()


def test_redact_args_truncates_long_values():
    clean = redact_args({"conteudo": "a" * 1000})
    assert clean["conteudo"].endswith("…")
    assert len(clean["conteudo"]) < 400


# Eventos ---------------------------------------------------------------------------
def test_event_bus_isolates_failing_subscriber():
    bus = EventBus()
    received = []

    def bad(_event):
        raise RuntimeError("cliente quebrado")

    bus.subscribe(bad)
    bus.subscribe(received.append)
    bus.emit("state", {"state": "processing"})
    assert received and received[0]["type"] == "state"
    assert bus.recent(1)[0]["payload"]["state"] == "processing"
