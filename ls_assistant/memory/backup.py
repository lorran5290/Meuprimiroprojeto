"""Exportação e importação de backups da memória (JSON legível).

- Exportar: grava todos os itens (inclusive sensíveis, marcados como tal).
- Importar em modo 'mesclar' (padrão): adiciona só o que não existe ainda.
- Importar em modo 'substituir': antes, faz um backup automático da memória atual.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ls_assistant.errors import LSError
from ls_assistant.memory.store import MemoryStore, normalize

FORMAT = "ls-memoria"
FORMAT_VERSION = 1


def export_backup(store: MemoryStore, target: Path) -> dict[str, Any]:
    memories = store.all_memories()
    payload = {
        "formato": FORMAT,
        "versao": FORMAT_VERSION,
        "exportado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contem_sensiveis": any(m.sensitive for m in memories),
        "memorias": [
            {
                "categoria": m.category,
                "chave": m.key,
                "conteudo": m.content,
                "tags": list(m.tags),
                "sensivel": m.sensitive,
                "origem": m.source,
                "criado_em": m.created_at,
                "atualizado_em": m.updated_at,
            }
            for m in memories
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(target), "count": len(memories)}


def _read_backup(source: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LSError(f"Não consegui ler o backup: {exc}") from exc
    if not isinstance(data, dict) or data.get("formato") != FORMAT:
        raise LSError("O arquivo não é um backup de memória do LS.")
    items = data.get("memorias")
    if not isinstance(items, list):
        raise LSError("Backup sem a lista 'memorias'.")
    return items


def import_backup(store: MemoryStore, source: Path, *, mode: str = "mesclar", backups_dir: Path | None = None) -> dict[str, int]:
    if mode not in {"mesclar", "substituir"}:
        raise LSError("Modo de importação inválido. Use 'mesclar' ou 'substituir'.")
    items = _read_backup(source)

    if mode == "substituir":
        if backups_dir is not None:
            export_backup(store, backups_dir / f"antes-da-importacao-{datetime.now():%Y%m%d-%H%M%S}.json")
        for memory in store.all_memories():
            store.delete(memory.id)

    existing = {(m.category, normalize(m.key), normalize(m.content)) for m in store.all_memories()}
    added = skipped = 0
    for item in items:
        try:
            category = str(item["categoria"])
            content = str(item["conteudo"])
        except (KeyError, TypeError):
            skipped += 1
            continue
        signature = (category, normalize(str(item.get("chave", ""))), normalize(content))
        if signature in existing:
            skipped += 1
            continue
        store.add(
            content,
            category=category,
            key=str(item.get("chave", "")),
            tags=tuple(item.get("tags", []) or []),
            sensitive=bool(item.get("sensivel", False)),
            source="importado",
        )
        existing.add(signature)
        added += 1
    return {"added": added, "skipped": skipped}
