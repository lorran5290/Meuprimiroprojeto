"""Arquivos (planos em duas etapas, quarentena reversível) e executor de ferramentas (política de segurança)."""

from __future__ import annotations

import threading
import time

import pytest
from pydantic import BaseModel

from ls_assistant.errors import LSError
from ls_assistant.desktop.files import FileService, PlanStore
from ls_assistant.events import EventBus
from ls_assistant.security import AuditLog, ConfirmationBroker, EmergencyStop, PathPolicy, Risk
from ls_assistant.tools.base import ActionResult, ToolSpec
from ls_assistant.tools.executor import ToolExecutor
from ls_assistant.tools.registry import ToolRegistry


@pytest.fixture
def files(sandbox):
    policy = PathPolicy([sandbox["docs"]])
    return FileService(policy, PlanStore(sandbox["data"] / "planos"), sandbox["data"] / "quarentena")


# Arquivos -----------------------------------------------------------------------
def test_list_and_read_text_document(files: FileService, sandbox):
    (sandbox["docs"] / "nota.txt").write_text("Olá, LS.\nSegunda linha.", encoding="utf-8")
    listing = files.list_dir(str(sandbox["docs"]))
    assert [i["nome"] for i in listing["itens"]] == ["nota.txt"]
    doc = files.read_document(str(sandbox["docs"] / "nota.txt"))
    assert "Segunda linha" in doc["texto"] and doc["truncado"] is False


def test_unsupported_format_is_refused(files: FileService, sandbox):
    (sandbox["docs"] / "programa.exe").write_bytes(b"MZ")
    with pytest.raises(LSError):
        files.read_document(str(sandbox["docs"] / "programa.exe"))


def test_search_finds_names_accent_insensitive(files: FileService, sandbox):
    (sandbox["docs"] / "Relatório Final.pdf").write_bytes(b"%PDF")
    (sandbox["docs"] / "outro.txt").write_text("x")
    found = files.search("relatorio")
    assert [r["nome"] for r in found["resultados"]] == ["Relatório Final.pdf"]


def test_create_never_overwrites(files: FileService, sandbox):
    files.create_text_file(str(sandbox["docs"] / "ata.md"), "primeira versão")
    with pytest.raises(LSError):
        files.create_text_file(str(sandbox["docs"] / "ata.md"), "sobrescrever?")
    assert (sandbox["docs"] / "ata.md").read_text(encoding="utf-8") == "primeira versão"


def test_create_refuses_non_text_extension(files: FileService, sandbox):
    with pytest.raises(LSError):
        files.create_text_file(str(sandbox["docs"] / "script.bat"), "echo oi")


def test_rename_move_copy_refuse_to_overwrite(files: FileService, sandbox):
    docs = sandbox["docs"]
    (docs / "a.txt").write_text("A")
    (docs / "pasta").mkdir()
    files.move(str(docs / "a.txt"), str(docs / "pasta"))
    assert (docs / "pasta" / "a.txt").exists() and not (docs / "a.txt").exists()
    files.copy(str(docs / "pasta" / "a.txt"), str(docs))
    assert (docs / "a.txt").exists()
    (docs / "b.txt").write_text("B")
    with pytest.raises(LSError):
        files.rename(str(docs / "b.txt"), "a.txt")
    with pytest.raises(LSError):
        files.copy(str(docs / "a.txt"), str(docs / "pasta"))  # já existe lá


def test_duplicates_are_found_by_content(files: FileService, sandbox):
    docs = sandbox["docs"]
    (docs / "foto.bin").write_bytes(b"mesmo conteudo")
    (docs / "copia de foto.bin").write_bytes(b"mesmo conteudo")
    (docs / "diferente.bin").write_bytes(b"outro")
    groups = files.find_duplicates(str(docs))["grupos"]
    assert len(groups) == 1 and len(groups[0]["arquivos"]) == 2


def test_organization_is_proposed_then_applied(files: FileService, sandbox):
    docs = sandbox["docs"]
    (docs / "contrato.pdf").write_bytes(b"%PDF-1")
    (docs / "foto.jpg").write_bytes(b"\xff\xd8")
    proposal = files.propose_organization(str(docs))
    assert proposal["total"] == 2
    assert (docs / "contrato.pdf").exists()  # proposta não move nada
    result = files.apply_plan(proposal["plano_id"])
    assert result["movidos"] == 2
    assert (docs / "Documentos" / "contrato.pdf").exists()
    assert (docs / "Imagens" / "foto.jpg").exists()
    with pytest.raises(LSError):
        files.apply_plan(proposal["plano_id"])  # plano já aplicado


def test_cleanup_goes_to_quarantine_and_can_be_restored(files: FileService, sandbox):
    docs = sandbox["docs"]
    victim = docs / "antigo.txt"
    victim.write_text("não é para apagar de vez")
    plan = files.prepare_cleanup([str(victim)])
    assert victim.exists()  # preparar não apaga
    result = files.send_to_quarantine(plan["plano_id"])
    assert result["movidos_para_quarentena"] == 1
    assert not victim.exists()
    restored = files.restore_quarantine(plan["plano_id"])
    assert restored["restaurados"] == 1
    assert victim.read_text(encoding="utf-8") == "não é para apagar de vez"


def test_root_folder_cannot_enter_cleanup_plan(files: FileService, sandbox):
    with pytest.raises(LSError):
        files.prepare_cleanup([str(sandbox["docs"])])


def test_paths_outside_roots_are_refused(files: FileService, sandbox):
    with pytest.raises(LSError):
        files.list_dir(str(sandbox["root"]))


# Executor -----------------------------------------------------------------------
class _Args(BaseModel):
    nome: str = ""


@pytest.fixture
def executor_env(sandbox):
    audit = AuditLog(sandbox["data"] / "audit.sqlite3")
    events = EventBus()
    broker = ConfirmationBroker(default_timeout_s=5, emit=events.emit)
    emergency = EmergencyStop(broker)
    registry = ToolRegistry()
    executor = ToolExecutor(registry, audit=audit, broker=broker, emergency=emergency, events=events,
                            default_timeout_s=0.5)
    yield {"registry": registry, "executor": executor, "audit": audit, "events": events,
           "broker": broker, "emergency": emergency}
    executor.shutdown()
    audit.close()


def _register(env, name: str, risk: Risk, handler, timeout: float | None = None):
    env["registry"].register(ToolSpec(name=name, title=name, description="teste", risk=risk,
                                      args_model=_Args, handler=handler, timeout_s=timeout))


def test_unknown_tool_and_invalid_args(executor_env):
    ex = executor_env["executor"]
    assert ex.execute("nao_existe", {}).status == "unknown_tool"
    _register(executor_env, "eco", Risk.READ, lambda a, c: ActionResult(a.nome))
    out = ex.execute("eco", {"nome": 123, "extra": object()})
    assert out.status in {"ok", "invalid_args"}  # pydantic coage 123 para texto
    bad = ex.execute("eco", {"nome": ["lista"]})
    assert bad.status == "invalid_args" and "nome" in bad.message


def test_read_tool_runs_and_is_audited(executor_env):
    _register(executor_env, "soma", Risk.READ, lambda a, c: ActionResult("feito", {"valor": 42}))
    out = executor_env["executor"].execute("soma", {"nome": "x"})
    assert out.ok and out.data == {"valor": 42}
    rows = executor_env["audit"].list()
    assert rows[0]["tool"] == "soma" and rows[0]["status"] == "ok"
    kinds = [e["type"] for e in executor_env["events"].recent()]
    assert kinds.count("tool") >= 2  # início e fim


def test_blocked_risk_never_runs(executor_env):
    ran = []
    _register(executor_env, "proibida", Risk.BLOCKED, lambda a, c: ran.append(1) or ActionResult("ok"))
    out = executor_env["executor"].execute("proibida", {})
    assert out.status == "denied" and ran == []


def test_confirm_tool_waits_for_approval_then_runs(executor_env):
    ran = []
    _register(executor_env, "apagar", Risk.CONFIRM, lambda a, c: ran.append(1) or ActionResult("apagado"))
    broker = executor_env["broker"]
    events = executor_env["events"]

    def approve_when_asked():
        for _ in range(100):
            pending = broker.pending()
            if pending:
                broker.resolve(pending[0]["id"], True)
                return
            time.sleep(0.02)

    threading.Thread(target=approve_when_asked, daemon=True).start()
    out = executor_env["executor"].execute("apagar", {"nome": "x"})
    assert out.status == "ok" and ran == [1]
    assert out.approval == "aprovado"
    assert any(e["type"] == "confirmation" and e["payload"].get("action") == "requested" for e in events.recent())


def test_confirm_tool_denied_does_not_run(executor_env):
    ran = []
    _register(executor_env, "apagar", Risk.CONFIRM, lambda a, c: ran.append(1) or ActionResult("apagado"))
    broker = executor_env["broker"]

    def refuse():
        for _ in range(100):
            pending = broker.pending()
            if pending:
                broker.resolve(pending[0]["id"], False)
                return
            time.sleep(0.02)

    threading.Thread(target=refuse, daemon=True).start()
    out = executor_env["executor"].execute("apagar", {"nome": "x"})
    assert out.status == "denied" and ran == []
    assert "Nada foi alterado" in out.message


def test_confirmation_timeout_is_a_denial(executor_env):
    executor_env["broker"]._default_timeout = 0.2
    _register(executor_env, "apagar", Risk.CONFIRM, lambda a, c: ActionResult("apagado"))
    out = executor_env["executor"].execute("apagar", {"nome": "x"})
    assert out.status == "denied" and "tempo esgotado" in out.approval


def test_timeout_is_reported_not_success(executor_env):
    def slow(a, c):
        time.sleep(1.5)
        return ActionResult("tarde demais")

    _register(executor_env, "lenta", Risk.READ, slow, timeout=0.2)
    out = executor_env["executor"].execute("lenta", {})
    assert out.status == "timeout" and not out.ok


def test_handler_exception_is_hidden_from_model(executor_env):
    def boom(a, c):
        raise RuntimeError("detalhe interno sensível")

    _register(executor_env, "quebra", Risk.READ, boom)
    out = executor_env["executor"].execute("quebra", {})
    assert out.status == "failed"
    assert "detalhe interno" not in out.message


def test_unverified_result_is_never_success(executor_env):
    from ls_assistant.tools.base import ToolUnverified

    def nao_confirmado(a, c):
        raise ToolUnverified("Pedido enviado, sem confirmação.")

    _register(executor_env, "abrir", Risk.REVERSIBLE, nao_confirmado)
    out = executor_env["executor"].execute("abrir", {})
    assert out.status == "unverified" and not out.ok


def test_emergency_blocks_new_actions(executor_env):
    _register(executor_env, "qualquer", Risk.READ, lambda a, c: ActionResult("ok"))
    executor_env["emergency"].trigger()
    out = executor_env["executor"].execute("qualquer", {})
    assert out.status == "cancelled"
    executor_env["emergency"].reset()
    assert executor_env["executor"].execute("qualquer", {}).ok
