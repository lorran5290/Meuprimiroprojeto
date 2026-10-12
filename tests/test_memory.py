"""Memória pessoal: busca, sensibilidade, contradições, correções, histórico, dados iniciais e backups."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ls_assistant.errors import LSError
from ls_assistant.memory import MemoryStore, SecretRefused, apply_seed_memories, export_backup, import_backup

FAKE_GOOGLE_KEY = "AI" + "za" + "Fake" + "0" * 30  # formato apenas; não é chave real


@pytest.fixture
def store(tmp_path: Path):
    s = MemoryStore(tmp_path / "mem.sqlite3")
    yield s
    s.close()


def test_add_stores_timestamps_and_category(store: MemoryStore):
    result = store.add("Quero respostas curtas no meu dia a dia.", category="preferencias", tags=["resposta", "estilo"])
    m = result.memory
    assert m.id >= 1 and m.category == "preferencias"
    assert m.created_at and m.updated_at
    assert m.tags == ("estilo", "resposta")


def test_unknown_category_is_rejected(store: MemoryStore):
    with pytest.raises(LSError):
        store.add("algo", category="categoria-inventada")


def test_secrets_are_refused(store: MemoryStore):
    with pytest.raises(SecretRefused):
        store.add("minha senha do banco é 1234", category="geral")
    with pytest.raises(SecretRefused):
        store.add("chave: " + FAKE_GOOGLE_KEY, category="geral")
    assert store.list() == []


def test_cpf_like_numbers_become_sensitive(store: MemoryStore):
    m = store.add("Meu CPF é 123.456.789-09.", category="profissional").memory
    assert m.sensitive is True


def test_sensitive_items_stay_out_of_recall_and_masked_in_public_view(store: MemoryStore):
    store.add("Endereço de cobrança da ExNet em Caju.", category="projetos", key="ExNet Fiber", sensitive=True)
    store.add("ExNet Fiber é um provedor de fibra.", category="projetos", key="ExNet Fiber")
    recalled = store.recall("ExNet Fiber")
    assert all(not m.sensitive for m in recalled)
    sensitive = [m for m in store.list() if m.sensitive][0]
    assert sensitive.public(mask_sensitive=True)["content"] == "••••••"


def test_search_ranks_key_matches_first_and_ignores_accents(store: MemoryStore):
    store.add("Negócio de alimentação com cardápios.", category="projetos", key="DOM CULINÁRIO")
    store.add("Um texto qualquer sobre culinária.", category="geral")
    results = store.search("dom culinario")
    assert results[0].key == "DOM CULINÁRIO"


def test_stopwords_do_not_create_false_matches(store: MemoryStore):
    store.add("Preciso revisar o contrato amanhã.", category="rotinas")
    assert store.search("o que você sabe sobre o") == []


def test_contradictions_are_reported_not_silently_overwritten(store: MemoryStore):
    store.add("Atendimento em Caju e Nova Iguaçu.", category="projetos", key="ExNet Fiber")
    result = store.add("Atendimento em Niterói.", category="projetos", key="ExNet Fiber")
    assert len(result.conflicts) == 1
    pairs = store.conflicts()
    assert len(pairs) == 1
    assert {pairs[0][0].content, pairs[0][1].content} == {"Atendimento em Caju e Nova Iguaçu.", "Atendimento em Niterói."}


def test_update_corrects_and_keeps_creation_date(store: MemoryStore):
    original = store.add("Versão antiga.", category="projetos", key="X").memory
    updated = store.update(original.id, content="Versão nova.")
    assert updated.content == "Versão nova."
    assert updated.created_at == original.created_at
    assert updated.key == "X"


def test_update_refuses_empty_content_and_secret(store: MemoryStore):
    m = store.add("Algo útil.", category="geral").memory
    with pytest.raises(LSError):
        store.update(m.id, content="   ")
    with pytest.raises(SecretRefused):
        store.update(m.id, content="token: abc")


def test_delete_removes_only_the_selected_item(store: MemoryStore):
    a = store.add("Primeiro.", category="geral").memory
    b = store.add("Segundo.", category="geral").memory
    assert store.delete(a.id) is True
    assert store.get(a.id) is None
    assert store.get(b.id) is not None


def test_persistence_survives_reopening(tmp_path: Path):
    path = tmp_path / "persist.sqlite3"
    first = MemoryStore(path)
    first.add("Informação de teste persistente.", category="geral", key="Teste")
    first.close()
    second = MemoryStore(path)
    assert [m.content for m in second.search("persistente")] == ["Informação de teste persistente."]
    second.close()


def test_conversation_history_can_be_logged_and_cleared(store: MemoryStore):
    store.log_message("usuario", "oi")
    store.log_message("ls", "olá")
    assert [m["role"] for m in store.recent_messages()] == ["usuario", "ls"]
    assert store.clear_history() == 2
    assert store.recent_messages() == []


def test_seed_is_applied_once_and_stays_editable(store: MemoryStore):
    assert apply_seed_memories(store) == 9
    assert apply_seed_memories(store) == 0
    names = {m.key for m in store.list()}
    assert {"ExNet Fiber", "DOM CULINÁRIO"} <= names
    exnet = store.search("ExNet Fiber", limit=20)
    assert any("Caju" in m.content and m.source == "seed" for m in exnet)
    dom = store.search("DOM CULINÁRIO", limit=20)
    assert any("@dom_culinario" in m.content for m in dom)
    # Apagar um item inicial não o devolve numa próxima inicialização.
    victim = store.search("iFood", limit=1)[0]
    store.delete(victim.id)
    assert apply_seed_memories(store) == 0
    assert store.search("iFood", limit=5) == []


def test_backup_export_and_merge_import(tmp_path: Path, store: MemoryStore):
    store.add("Gosto de respostas objetivas.", category="preferencias", key="Estilo")
    backup = tmp_path / "backup.json"
    export_backup(store, backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload["formato"] == "ls-memoria" and len(payload["memorias"]) == 1

    other = MemoryStore(tmp_path / "outra.sqlite3")
    result = import_backup(other, backup, mode="mesclar")
    assert result == {"added": 1, "skipped": 0}
    again = import_backup(other, backup, mode="mesclar")
    assert again == {"added": 0, "skipped": 1}  # mesclar não duplica
    other.close()


def test_backup_replace_keeps_safety_copy(tmp_path: Path, store: MemoryStore):
    store.add("Atual.", category="geral")
    backup = tmp_path / "novo.json"
    backup.write_text(json.dumps({"formato": "ls-memoria", "versao": 1, "memorias": [
        {"categoria": "geral", "chave": "", "conteudo": "Vindo do backup.", "tags": [], "sensivel": False}]}), encoding="utf-8")
    backups_dir = tmp_path / "backups"
    import_backup(store, backup, mode="substituir", backups_dir=backups_dir)
    assert [m.content for m in store.list()] == ["Vindo do backup."]
    safety = list(backups_dir.glob("antes-da-importacao-*.json"))
    assert len(safety) == 1


def test_invalid_backup_file_is_rejected(tmp_path: Path, store: MemoryStore):
    bad = tmp_path / "errado.json"
    bad.write_text('{"nao": "e um backup"}', encoding="utf-8")
    with pytest.raises(LSError):
        import_backup(store, bad)
