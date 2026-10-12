"""Operações de arquivos dentro das pastas permitidas.

Regras:
- Todo caminho passa pela PathPolicy.
- Nada é apagado permanentemente. "Excluir" = mover para a quarentena do LS,
  com possibilidade de restaurar.
- Organização e exclusão são feitas em duas etapas: primeiro um plano
  (somente leitura), depois a aplicação, que exige aprovação.
- Sobrescrever arquivo existente nunca acontece em silêncio: a operação é recusada.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ls_assistant.errors import LSError
from ls_assistant.memory.store import normalize
from ls_assistant.security import CancelToken, PathPolicy
from ls_assistant.security.paths import BLOCKED_PARTS

TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".csv", ".json", ".log", ".py", ".html", ".htm", ".xml", ".ini", ".yaml", ".yml", ".js", ".ts", ".css"}
)
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | {".pdf"}
MAX_READ_CHARS = 20_000
MAX_VISITED = 50_000

ORGANIZE_GROUPS: dict[str, frozenset[str]] = {
    "Imagens": frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"}),
    "Documentos": frozenset({".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"}),
    "Planilhas": frozenset({".xls", ".xlsx", ".csv", ".ods"}),
    "Apresentacoes": frozenset({".ppt", ".pptx", ".odp"}),
    "Audio": frozenset({".mp3", ".wav", ".m4a", ".flac", ".ogg"}),
    "Video": frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm"}),
    "Compactados": frozenset({".zip", ".rar", ".7z", ".tar", ".gz"}),
}
ORGANIZE_GROUP_NAMES = frozenset(ORGANIZE_GROUPS)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PlanStore:
    """Planos de organização e exclusão, salvos em JSON para continuar entre sessões."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, kind: str, items: list[dict[str, Any]], summary: str) -> dict[str, Any]:
        plan = {
            "id": uuid.uuid4().hex[:8],
            "kind": kind,
            "status": "preparado",
            "created_at": _iso_now(),
            "summary": summary,
            "items": items,
        }
        self._write(plan)
        return plan

    def load(self, plan_id: str) -> dict[str, Any]:
        if not plan_id.isalnum():
            raise LSError("Identificador de plano inválido.")
        path = self._dir / f"{plan_id}.json"
        if not path.exists():
            raise LSError(f"Plano '{plan_id}' não encontrado.")
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, plan: dict[str, Any]) -> None:
        self._write(plan)

    def _write(self, plan: dict[str, Any]) -> None:
        (self._dir / f"{plan['id']}.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


class FileService:
    def __init__(self, policy: PathPolicy, plans: PlanStore, quarantine_dir: Path) -> None:
        self._policy = policy
        self._plans = plans
        self._quarantine = quarantine_dir

    # Leitura ----------------------------------------------------------------
    def list_dir(self, raw: str, pattern: str = "*", limit: int = 200) -> dict[str, Any]:
        folder = self._policy.check(raw or str(self._policy.default_root), must_exist=True)
        if not folder.is_dir():
            raise LSError(f"'{folder.name}' não é uma pasta.")
        entries = []
        for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if pattern and not fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                continue
            entries.append(self._describe(entry))
            if len(entries) >= limit:
                break
        return {"pasta": str(folder), "itens": entries, "total": len(entries)}

    def search(self, term: str, root: str = "", limit: int = 50, cancel: CancelToken | None = None) -> dict[str, Any]:
        needle = normalize(term)
        if not needle:
            raise LSError("Informe um termo para pesquisar.")
        start = self._policy.check(root or str(self._policy.default_root), must_exist=True)
        found: list[dict[str, Any]] = []
        visited = 0
        for dirpath, dirnames, filenames in os.walk(start):
            if cancel is not None:
                cancel.raise_if_cancelled()
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in self._blocked()]
            for name in dirnames + filenames:
                visited += 1
                if needle in normalize(name):
                    found.append(self._describe(Path(dirpath) / name))
                    if len(found) >= limit:
                        return {"termo": term, "resultados": found, "limite_atingido": True, "visitados": visited}
            if visited >= MAX_VISITED:
                break
        return {"termo": term, "resultados": found, "limite_atingido": False, "visitados": visited}

    def read_document(self, raw: str, max_chars: int = 8000) -> dict[str, Any]:
        path = self._policy.check(raw, must_exist=True)
        if not path.is_file():
            raise LSError(f"'{path.name}' não é um arquivo.")
        limit = max(200, min(max_chars, MAX_READ_CHARS))
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = self._read_pdf(path, limit)
        elif suffix in TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raise LSError(f"Formato '{suffix or 'sem extensão'}' não é suportado para leitura.")
        truncated = len(text) > limit
        return {"arquivo": str(path), "texto": text[:limit], "truncado": truncated, "caracteres": len(text)}

    def find_duplicates(self, raw: str, limit_groups: int = 30, cancel: CancelToken | None = None) -> dict[str, Any]:
        root = self._policy.check(raw or str(self._policy.default_root), must_exist=True)
        by_size: dict[int, list[Path]] = defaultdict(list)
        visited = 0
        for dirpath, dirnames, filenames in os.walk(root):
            if cancel is not None:
                cancel.raise_if_cancelled()
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                visited += 1
                path = Path(dirpath) / name
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > 0:
                    by_size[size].append(path)
                if visited >= MAX_VISITED:
                    break
        groups: list[dict[str, Any]] = []
        for size, paths in by_size.items():
            if len(paths) < 2:
                continue
            by_hash: dict[str, list[Path]] = defaultdict(list)
            for path in paths:
                if cancel is not None:
                    cancel.raise_if_cancelled()
                by_hash[self._sha256(path)].append(path)
            for digest, same in by_hash.items():
                if len(same) > 1:
                    groups.append({"tamanho_bytes": size, "hash": digest[:16], "arquivos": [str(p) for p in same]})
                    if len(groups) >= limit_groups:
                        return {"grupos": groups, "limite_atingido": True, "visitados": visited}
        return {"grupos": groups, "limite_atingido": False, "visitados": visited}

    # Criação e alteração simples ------------------------------------------
    def create_folder(self, raw: str) -> dict[str, Any]:
        path = self._policy.check(raw)
        if path.exists():
            return {"caminho": str(path), "ja_existia": True}
        path.mkdir(parents=True)
        return {"caminho": str(path), "ja_existia": False}

    def create_text_file(self, raw: str, content: str) -> dict[str, Any]:
        path = self._policy.check(raw)
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            raise LSError("Só crio arquivos de texto (.txt, .md, .csv, .json, .html etc.).")
        if path.exists():
            raise LSError(f"'{path.name}' já existe. Não sobrescrevo arquivos em silêncio.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"caminho": str(path), "bytes": path.stat().st_size}

    def rename(self, raw: str, new_name: str) -> dict[str, Any]:
        source = self._policy.check(raw, must_exist=True)
        if not new_name or any(sep in new_name for sep in ("/", "\\")):
            raise LSError("O novo nome não pode conter barras.")
        target = self._policy.check(source.parent / new_name)
        if target.exists():
            raise LSError(f"Já existe um item chamado '{new_name}'.")
        source.rename(target)
        return {"de": str(source), "para": str(target)}

    def move(self, raw_source: str, raw_dest_dir: str) -> dict[str, Any]:
        source = self._policy.check(raw_source, must_exist=True)
        dest_dir = self._policy.check(raw_dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / source.name
        if target.exists():
            raise LSError(f"Já existe '{source.name}' na pasta de destino. Nada foi movido.")
        shutil.move(str(source), str(self._policy.check(target)))
        return {"de": str(source), "para": str(target)}

    def copy(self, raw_source: str, raw_dest_dir: str) -> dict[str, Any]:
        source = self._policy.check(raw_source, must_exist=True)
        if not source.is_file():
            raise LSError("Por enquanto só copio arquivos individuais.")
        dest_dir = self._policy.check(raw_dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / source.name
        if target.exists():
            raise LSError(f"Já existe '{source.name}' na pasta de destino. Nada foi copiado.")
        shutil.copy2(source, self._policy.check(target))
        return {"de": str(source), "para": str(target)}

    # Planos (duas etapas) -----------------------------------------------------
    def propose_organization(self, raw_folder: str) -> dict[str, Any]:
        folder = self._policy.check(raw_folder, must_exist=True)
        if not folder.is_dir():
            raise LSError("Preciso de uma pasta para organizar.")
        items: list[dict[str, Any]] = []
        for entry in sorted(folder.iterdir()):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            group = next((g for g, exts in ORGANIZE_GROUPS.items() if entry.suffix.lower() in exts), "Outros")
            target = folder / group / entry.name
            if target.exists():
                continue  # conflito: mantém o arquivo onde está
            items.append({"de": str(entry), "para": str(target), "grupo": group})
        summary = f"{len(items)} arquivo(s) seriam movidos em '{folder.name}'."
        plan = self._plans.save("organizacao", items, summary)
        return {"plano_id": plan["id"], "resumo": summary, "movimentos": items[:50], "total": len(items)}

    def apply_plan(self, plan_id: str) -> dict[str, Any]:
        plan = self._plans.load(plan_id)
        if plan["kind"] != "organizacao":
            raise LSError("Este plano não é de organização.")
        if plan["status"] != "preparado":
            raise LSError(f"O plano já está '{plan['status']}'.")
        done, skipped = [], []
        for item in plan["items"]:
            try:
                source = self._policy.check(item["de"], must_exist=True)
                target = self._policy.check(item["para"])
                if target.exists():
                    skipped.append({"arquivo": item["de"], "motivo": "destino já existe"})
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                item["executado"] = True
                done.append(str(target))
            except LSError as exc:
                skipped.append({"arquivo": item["de"], "motivo": str(exc)})
        plan["status"] = "aplicado"
        plan["applied_at"] = _iso_now()
        self._plans.update(plan)
        return {"plano_id": plan_id, "movidos": len(done), "ignorados": skipped}

    def prepare_cleanup(self, raw_paths: list[str]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for raw in raw_paths:
            path = self._policy.check(raw, must_exist=True)
            if self._policy.is_root(path):
                raise LSError(f"'{path}' é uma pasta raiz permitida e não pode entrar em exclusão.")
            size = self._size(path)
            items.append({"caminho": str(path), "tipo": "pasta" if path.is_dir() else "arquivo", "tamanho_bytes": size})
        total = sum(i["tamanho_bytes"] for i in items)
        summary = f"{len(items)} item(ns) preparados para a quarentena (~{total / 1_048_576:.1f} MB). Nada foi apagado."
        plan = self._plans.save("exclusao", items, summary)
        return {"plano_id": plan["id"], "resumo": summary, "itens": items}

    def send_to_quarantine(self, plan_id: str) -> dict[str, Any]:
        plan = self._plans.load(plan_id)
        if plan["kind"] != "exclusao":
            raise LSError("Este plano não é de exclusão.")
        if plan["status"] != "preparado":
            raise LSError(f"O plano já está '{plan['status']}'.")
        folder = self._quarantine / plan["id"]
        folder.mkdir(parents=True, exist_ok=True)
        moved, skipped = [], []
        for item in plan["items"]:
            try:
                source = self._policy.check(item["caminho"], must_exist=True)
            except LSError as exc:
                skipped.append({"arquivo": item["caminho"], "motivo": str(exc)})
                continue
            target = folder / source.name
            counter = 1
            while target.exists():
                target = folder / f"{source.stem} ({counter}){source.suffix}"
                counter += 1
            shutil.move(str(source), str(target))
            item["quarentena"] = str(target)
            moved.append(str(target))
        plan["status"] = "em_quarentena"
        plan["quarantined_at"] = _iso_now()
        self._plans.update(plan)
        return {"plano_id": plan_id, "movidos_para_quarentena": len(moved), "ignorados": skipped,
                "observacao": "Itens podem ser restaurados com restaurar_quarentena."}

    def restore_quarantine(self, plan_id: str) -> dict[str, Any]:
        plan = self._plans.load(plan_id)
        if plan["status"] != "em_quarentena":
            raise LSError("Este plano não está na quarentena.")
        restored, skipped = [], []
        for item in plan["items"]:
            quarantined, original = item.get("quarentena"), Path(item["caminho"])
            if not quarantined or not Path(quarantined).exists():
                skipped.append({"arquivo": item["caminho"], "motivo": "não encontrado na quarentena"})
                continue
            if original.exists():
                skipped.append({"arquivo": item["caminho"], "motivo": "já existe um item no local original"})
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(quarantined, str(original))
            restored.append(str(original))
        plan["status"] = "restaurado" if not skipped else "restauracao_parcial"
        self._plans.update(plan)
        return {"plano_id": plan_id, "restaurados": len(restored), "ignorados": skipped}

    # Auxiliares ----------------------------------------------------------------
    def _describe(self, path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
            size, modified = stat.st_size, datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes")
        except OSError:
            size, modified = 0, ""
        return {
            "nome": path.name,
            "caminho": str(path),
            "tipo": "pasta" if path.is_dir() else "arquivo",
            "tamanho_bytes": size,
            "modificado": modified,
        }

    @staticmethod
    def _blocked() -> frozenset[str]:
        return BLOCKED_PARTS

    @staticmethod
    def _size(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for name in filenames:
                try:
                    total += (Path(dirpath) / name).stat().st_size
                except OSError:
                    pass
        return total

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _read_pdf(path: Path, limit: int) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - depende da instalação
            raise LSError("Leitura de PDF requer o pacote pypdf. Rode: pip install -r requirements.txt") from exc
        reader = PdfReader(str(path))
        pieces: list[str] = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            pieces.append(text)
            total += len(text)
            if total > limit * 2:
                break
        return "\n".join(pieces)
