"""Voz (sem microfone real), aplicativos/janelas/shell (backends simulados) e API/WebSocket com token."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ls_assistant.desktop import shell
from ls_assistant.desktop.apps import AppCatalog, AppLauncher
from ls_assistant.desktop.windows import WindowInfo, WindowManager
from ls_assistant.errors import LSError
from ls_assistant.voice.listener import AWAKE, STANDBY, VoiceListener, rms
from ls_assistant.voice.tts import NullTTS, _encoded
from ls_assistant.voice.wake import WakeWordMatcher


# Palavra de ativação --------------------------------------------------------------
class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_wake_word_matches_whole_words_only():
    m = WakeWordMatcher(["ls", "ele esse"])
    assert m.matches("LS, abra o navegador")
    assert m.matches("ei ele esse, tudo bem")
    assert not m.matches("lsbo qualquer coisa")  # não é a palavra inteira
    assert not m.matches("eles chegaram")


def test_wake_word_cooldown_prevents_false_retriggers():
    clock = FakeClock()
    m = WakeWordMatcher(["ls"], cooldown_s=2.5, clock=clock)
    assert m.try_trigger("ls") is True
    clock.now += 1.0
    assert m.try_trigger("ls") is False  # dentro do cooldown
    clock.now += 2.0
    assert m.try_trigger("ls") is True


def test_strip_wake_removes_only_leading_phrase():
    m = WakeWordMatcher(["ls", "ele esse"])
    assert m.strip_wake("LS, abra o navegador") == "abra o navegador"
    assert m.strip_wake("ele esse, status do sistema") == "status do sistema"
    assert m.strip_wake("abra o LS") == "abra o LS"


def test_grammar_limits_recognizer_vocabulary():
    assert WakeWordMatcher(["ls", "ele esse"]).grammar() == ["ls", "ele esse", "[unk]"]


class FakeRecognizer:
    """Reconhecedor de mentira com o mesmo formato do Vosk."""

    def __init__(self, scripted):
        self.scripted = list(scripted)  # lista de (aceitou_final, texto)
        self.current = ("", False)

    def AcceptWaveform(self, data):
        if self.scripted:
            accepted, text = self.scripted.pop(0)
            self.current = (text, accepted)
            return accepted
        self.current = ("", False)
        return False

    def Result(self):
        return json.dumps({"text": self.current[0]})

    def PartialResult(self):
        return json.dumps({"partial": self.current[0]})

    def FinalResult(self):
        return json.dumps({"text": self.current[0]})


LOUD = (b"\xff\x7f" * 2000)  # amplitude alta
SILENT = b"\x00\x00" * 2000


def _listener(wake_script, command_script, clock, *, wake_enabled=True, commands=None, wakes=None, states=None):
    matcher = WakeWordMatcher(["ls"], cooldown_s=0, clock=clock)
    return VoiceListener(
        make_wake_recognizer=lambda: FakeRecognizer(wake_script),
        make_command_recognizer=lambda: FakeRecognizer(command_script),
        matcher=matcher,
        on_wake=lambda: (wakes if wakes is not None else []).append(1),
        on_command=lambda text: (commands if commands is not None else []).append(text),
        on_state=lambda s: (states if states is not None else []).append(s),
        energy_threshold=300,
        command_timeout_s=3,
        wake_enabled=wake_enabled,
        clock=clock,
    )


def test_rms_distinguishes_silence_from_speech():
    assert rms(SILENT) == 0
    assert rms(LOUD) > 300


def test_silence_never_reaches_the_recognizer():
    clock = FakeClock()
    touched = []

    class Spy(FakeRecognizer):
        def AcceptWaveform(self, data):
            touched.append(1)
            return False

    matcher = WakeWordMatcher(["ls"], clock=clock)
    listener = VoiceListener(make_wake_recognizer=Spy, make_command_recognizer=Spy, matcher=matcher,
                             on_wake=lambda: None, on_command=lambda t: None, clock=clock)
    for _ in range(5):
        listener.feed(SILENT)
    assert touched == []


def test_wake_word_then_command_flow():
    clock = FakeClock()
    commands, wakes, states = [], [], []
    listener = _listener([(False, "ls")], [(True, "LS abra o navegador")], clock,
                         commands=commands, wakes=wakes, states=states)
    listener.feed(LOUD)  # acorda
    assert wakes == [1] and listener.state == AWAKE
    listener.feed(LOUD)  # comando completo
    assert commands == ["abra o navegador"]
    assert listener.state == STANDBY
    assert states == [AWAKE, "ouvindo", STANDBY]  # 'ouvindo' = comando capturado, depois volta à espera


def test_no_wake_when_wake_word_disabled_but_button_still_works():
    clock = FakeClock()
    commands, wakes = [], []
    listener = _listener([(False, "ls")], [(True, "status do sistema")], clock, wake_enabled=False,
                         commands=commands, wakes=wakes)
    listener.feed(LOUD)
    assert wakes == [] and listener.state == STANDBY
    listener.request_command()
    listener.feed(LOUD)
    assert commands == ["status do sistema"]


def test_awake_without_speech_times_out_to_standby():
    clock = FakeClock()
    commands = []
    listener = _listener([(False, "ls")], [(False, "")], clock, commands=commands)
    listener.feed(LOUD)
    assert listener.state == AWAKE
    clock.now += 10  # passou do tempo limite
    listener.feed(LOUD)
    assert listener.state == STANDBY and commands == []


def test_cancel_command_returns_to_standby():
    clock = FakeClock()
    listener = _listener([(False, "ls")], [(False, "")], clock)
    listener.feed(LOUD)
    listener.cancel_command()
    assert listener.state == STANDBY


# Fala ------------------------------------------------------------------------------
def test_null_tts_is_honest_about_unavailability():
    tts = NullTTS()
    assert tts.available is False
    assert tts.speak("oi") is False
    assert tts.list_voices() == []


def test_speech_script_is_passed_encoded_not_interpolated():
    # O texto do usuário nunca é colocado dentro do script; só entra por stdin.
    encoded = _encoded("Write-Host 'x'")
    import base64

    assert base64.b64decode(encoded).decode("utf-16-le") == "Write-Host 'x'"


# Aplicativos ------------------------------------------------------------------------
@pytest.fixture
def start_menu(tmp_path: Path) -> Path:
    base = tmp_path / "Programs"
    base.mkdir()
    (base / "Spotify.lnk").write_bytes(b"lnk")
    (base / "Bloco de Notas Extra.lnk").write_bytes(b"lnk")
    return base


def test_catalog_finds_by_name_accent_insensitively(start_menu):
    catalog = AppCatalog([start_menu])
    names = [e.name for e in catalog.find("spotify")]
    assert names == ["Spotify"]
    assert catalog.find("qualquercoisa123") == []


def test_alias_is_opened_and_verified_by_pid():
    class Proc:
        pid = 4242

    alive = {4242}
    launcher = AppLauncher(AppCatalog([]), popen=lambda args: Proc(), sleep=lambda s: None, verify_timeout_s=0.5)
    import ls_assistant.desktop.apps as apps_mod

    original = apps_mod._pid_alive
    apps_mod._pid_alive = lambda pid: pid in alive
    try:
        result = launcher.open("calculadora")
    finally:
        apps_mod._pid_alive = original
    assert result["status"] == "verificado" and result["pid"] == 4242


def test_app_that_does_not_stay_open_is_reported_unverified():
    class Proc:
        pid = 1

    launcher = AppLauncher(AppCatalog([]), popen=lambda args: Proc(), sleep=lambda s: None, verify_timeout_s=0.05)
    import ls_assistant.desktop.apps as apps_mod

    original = apps_mod._pid_alive
    apps_mod._pid_alive = lambda pid: False
    try:
        result = launcher.open("bloco de notas")
    finally:
        apps_mod._pid_alive = original
    assert result["status"] == "nao_verificado"


def test_shortcut_launch_is_verified_by_new_process(start_menu):
    running = {"spotify.exe"}
    opened = []

    def snapshot():
        return set(running)

    def startfile(path):
        opened.append(path)
        running.add("spotify.exe")

    launcher = AppLauncher(AppCatalog([start_menu]), startfile=startfile, process_names=snapshot,
                           sleep=lambda s: None, verify_timeout_s=0.5)
    running.clear()
    result = launcher.open("Spotify")
    assert opened and result["status"] == "verificado"


def test_ambiguous_app_name_asks_instead_of_guessing(tmp_path):
    base = tmp_path / "Programs"
    base.mkdir()
    (base / "Editor Alfa.lnk").write_bytes(b"lnk")
    (base / "Editor Beta.lnk").write_bytes(b"lnk")
    opened = []
    launcher = AppLauncher(AppCatalog([base]), startfile=lambda p: opened.append(p), process_names=lambda: set(),
                           sleep=lambda s: None, verify_timeout_s=0.01)
    with pytest.raises(LSError) as info:
        launcher.open("editor")
    assert "Qual deles" in str(info.value)
    assert opened == []  # nada foi aberto por palpite


# Janelas -----------------------------------------------------------------------------
class FakeWindows:
    def __init__(self, windows):
        self.windows = list(windows)
        self.calls = []

    def list_windows(self):
        return list(self.windows)

    def show(self, handle, command):
        self.calls.append(("show", handle, command))
        for i, w in enumerate(self.windows):
            if w.handle == handle:
                self.windows[i] = WindowInfo(w.handle, w.title, w.pid, minimized=(command == 6), maximized=(command == 3))

    def activate(self, handle):
        self.calls.append(("activate", handle))
        return True

    def close(self, handle):
        self.calls.append(("close", handle))
        self.windows = [w for w in self.windows if w.handle != handle]

    def is_hung(self, handle):
        return False


def test_window_minimize_is_verified_and_ambiguity_is_reported():
    fake = FakeWindows([WindowInfo(1, "Documento - Word", 10, False, False),
                        WindowInfo(2, "Planilha - Word", 11, False, False)])
    manager = WindowManager(fake)
    with pytest.raises(LSError):
        manager.minimize("Word")  # duas janelas
    result = manager.minimize("Documento")
    assert result == {"status": "verificado", "janela": "Documento - Word", "estado": "minimizada"}


def test_close_reports_when_window_still_open():
    class Stubborn(FakeWindows):
        def close(self, handle):
            self.calls.append(("close", handle))  # não remove a janela

    manager = WindowManager(Stubborn([WindowInfo(1, "Notas", 10, False, False)]))
    result = manager.close("Notas")
    assert result["status"] == "nao_verificado"


# Shell -------------------------------------------------------------------------------
def test_urls_are_restricted_to_web_schemes():
    assert shell.normalize_url("exemplo.com.br") == "https://exemplo.com.br"
    with pytest.raises(LSError):
        shell.normalize_url("file:///C:/Windows/system.ini")
    with pytest.raises(LSError):
        shell.normalize_url("javascript:alert(1)")


def test_search_url_is_encoded():
    assert shell.search_url("ferramentas de IA para sites") == "https://www.google.com/search?q=ferramentas+de+IA+para+sites"


# Sistema -----------------------------------------------------------------------------
def test_system_status_reports_real_data_and_honest_temperature():
    from ls_assistant.desktop import system_info

    status = system_info.system_status()
    assert 0 <= status["memoria"]["uso_percent"] <= 100
    assert "disponivel" in status["temperatura"]
    assert isinstance(status["discos"], list)


# API e WebSocket ------------------------------------------------------------------------
@pytest.fixture
def client(ctx):
    from fastapi.testclient import TestClient

    from ls_assistant.ui.server import create_app

    token = "token-de-teste-" + "x" * 16
    app = create_app(ctx, token)
    tc = TestClient(app, base_url="http://127.0.0.1")
    tc.headers.update({"X-LS-Token": token})
    tc.token = token  # type: ignore[attr-defined]
    yield tc


def test_api_rejects_missing_or_wrong_token(ctx):
    from fastapi.testclient import TestClient

    from ls_assistant.ui.server import create_app

    tc = TestClient(create_app(ctx, "certo-" + "y" * 20), base_url="http://127.0.0.1")
    assert tc.get("/api/status").status_code == 401
    assert tc.get("/api/status", headers={"X-LS-Token": "errado"}).status_code == 401


def test_host_header_protection_blocks_dns_rebinding(ctx):
    from fastapi.testclient import TestClient

    from ls_assistant.ui.server import create_app

    tc = TestClient(create_app(ctx, "t" * 30), base_url="http://evil.example")
    assert tc.get("/").status_code == 400


def test_status_never_exposes_the_api_key(client, ctx):
    body = client.get("/api/status").json()
    assert "AQ." not in json.dumps(body)
    assert body["ia"]["ativa"] is False  # sem chave na fixture


def test_chat_reports_busy_and_runs_in_background(client, ctx):
    response = client.post("/api/chat", json={"texto": "status do sistema"})
    assert response.status_code == 202
    assert "tarefa" in response.json()
    for _ in range(100):
        if not ctx.runner.busy:
            break
        time.sleep(0.05)
    msgs = [e for e in ctx.events.recent() if e["type"] == "message" and e["payload"]["role"] == "ls"]
    assert msgs, "o LS deveria responder mesmo sem IA (modo local)"


def test_memory_crud_through_api(client):
    created = client.post("/api/memorias", json={"conteudo": "Gosto de café sem açúcar.", "categoria": "preferencias"})
    assert created.status_code == 201
    mid = created.json()["memoria"]["id"]
    found = client.get("/api/memorias", params={"consulta": "café"}).json()
    assert any(m["id"] == mid for m in found)
    patched = client.patch(f"/api/memorias/{mid}", json={"conteudo": "Gosto de café com pouco açúcar."})
    assert patched.json()["content"].startswith("Gosto de café com pouco")
    assert client.delete(f"/api/memorias/{mid}").json() == {"apagada": True}
    assert client.delete(f"/api/memorias/{mid}").status_code == 404


def test_memory_api_refuses_secrets(client):
    response = client.post("/api/memorias", json={"conteudo": "minha senha é 1234", "categoria": "geral"})
    assert response.status_code == 422


def test_settings_api_rejects_unknown_and_secret_fields(client):
    assert client.patch("/api/configuracoes", json={"valores": {"gemini_api_key": "x"}}).status_code == 422
    ok = client.patch("/api/configuracoes", json={"valores": {"effects_intensity": 0.4}})
    assert ok.status_code == 200 and ok.json()["effects_intensity"] == 0.4
    assert "gemini_api_key" not in ok.json()


def test_import_is_restricted_to_allowed_folders(client, tmp_path):
    outside = tmp_path / "fora.json"
    outside.write_text("{}", encoding="utf-8")
    response = client.post("/api/memorias/importar", json={"caminho": str(outside), "modo": "mesclar"})
    assert response.status_code == 422


def test_confirmation_endpoint_resolves_pending_action(client, ctx):
    req = ctx.broker.request(title="Teste", description="aprovar?", risk="confirmacao")
    assert client.get("/api/confirmacoes").json()[0]["id"] == req.id
    assert client.post(f"/api/confirmacoes/{req.id}", json={"aprovado": True}).status_code == 200
    assert ctx.broker.wait(req) is True
    assert client.post(f"/api/confirmacoes/{req.id}", json={"aprovado": True}).status_code == 404


def test_websocket_requires_token_and_streams_events(client, ctx):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=errado"):
            pass
    url = f"/ws?token={client.token}"  # type: ignore[attr-defined]
    with client.websocket_connect(url, headers={"host": "127.0.0.1"}) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        ctx.events.emit("state", {"state": "processing"})
        seen = []
        for _ in range(20):
            event = ws.receive_json()
            seen.append(event)
            if event["type"] == "state" and event["payload"].get("state") == "processing":
                break
        assert any(e["type"] == "state" for e in seen)


def test_emergency_endpoint_cancels_and_release_restores(client, ctx):
    token = ctx.emergency.new_token()
    response = client.post("/api/emergencia")
    assert response.status_code == 200
    assert token.cancelled
    assert response.json()["tasks_cancelled"] >= 1
    assert client.get("/api/status").json()["emergencia"] is True
    # Com a parada ativa, um pedido novo é recusado com explicação.
    blocked = client.post("/api/chat", json={"texto": "status do sistema"})
    assert blocked.status_code == 423
    assert client.post("/api/emergencia/liberar").json() == {"ativa": False}
    assert client.get("/api/status").json()["emergencia"] is False
