"""Memória pessoal persistente em SQLite.

Princípios:
- Só guarda o que o usuário forneceu, autorizou importar ou habilitou por integração.
- Senhas, tokens e chaves de API são recusados.
- Itens marcados como sensíveis ficam fora do contexto enviado ao modelo.
- Contradições (mesma chave, conteúdos diferentes) são detectadas e reportadas.
- Datas de criação e atualização são mantidas em UTC.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ls_assistant.errors import LSError

CATEGORIES: dict[str, str] = {
    "preferencias": "Preferências pessoais autorizadas",
    "projetos": "Projetos em andamento",
    "profissional": "Informações profissionais",
    "rotinas": "Rotinas e tarefas",
    "conversas": "Histórico de conversas selecionadas",
    "instrucoes": "Instruções recorrentes",
    "arquivos": "Arquivos e documentos autorizados",
    "geral": "Outras informações",
}

_SECRET_RE = re.compile(
    r"(\b(senhas?|password|passwd|pwd|tokens?|api[\s_-]?key|secrets?|credenciais?)\b|"
    r"AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{10,})",
    re.IGNORECASE,
)
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_STOPWORDS = frozenset(
    "o a os as de do da dos das e em um uma uns umas para pra por que qual quais "
    "sobre me meu minha seu sua é ser ter foi isso esse essa com no na nos nas "
    "ao aos à mais muito sei você voce lembra lembrar sabe".split()
)


class SecretRefused(LSError):
    """Conteúdo com cara de senha, token ou chave: não é guardado."""


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, espaços colapsados — para comparar textos."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_marks).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9@_.\-]+", normalize(text)) if len(t) >= 2 and t not in _STOPWORDS]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Memory:
    id: int
    category: str
    key: str
    content: str
    tags: tuple[str, ...]
    sensitive: bool
    source: str
    created_at: str
    updated_at: str

    def public(self, *, mask_sensitive: bool = False) -> dict[str, Any]:
        hidden = mask_sensitive and self.sensitive
        return {
            "id": self.id,
            "category": self.category,
            "category_label": CATEGORIES.get(self.category, self.category),
            "key": self.key,
            "content": "••••••" if hidden else self.content,
            "tags": list(self.tags),
            "sensitive": self.sensitive,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AddResult:
    memory: Memory
    conflicts: list[Memory] = field(default_factory=list)


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memorias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL,
                    chave TEXT NOT NULL DEFAULT '',
                    conteudo TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    sensivel INTEGER NOT NULL DEFAULT 0,
                    origem TEXT NOT NULL DEFAULT 'usuario',
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memorias_categoria ON memorias(categoria);
                CREATE TABLE IF NOT EXISTS mensagens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criado_em TEXT NOT NULL,
                    papel TEXT NOT NULL,
                    texto TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meta (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );
                """
            )

    @property
    def path(self) -> Path:
        return self._db_path

    # Escrita -------------------------------------------------------------
    def add(
        self,
        content: str,
        *,
        category: str = "geral",
        key: str = "",
        tags: tuple[str, ...] | list[str] = (),
        sensitive: bool = False,
        source: str = "usuario",
    ) -> AddResult:
        content = content.strip()
        if not content:
            raise LSError("O conteúdo da memória não pode ser vazio.")
        if _SECRET_RE.search(content) or _SECRET_RE.search(key):
            raise SecretRefused("Não guardo senhas, tokens ou chaves de API na memória.")
        category = self._check_category(category)
        if _CPF_RE.search(content):
            sensitive = True  # dados pessoais numéricos entram como sensíveis automaticamente
        key = key.strip()
        tag_text = ",".join(sorted({t.strip().lower() for t in tags if t.strip()}))
        now = _now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO memorias (categoria, chave, conteudo, tags, sensivel, origem, criado_em, atualizado_em)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (category, key, content, tag_text, int(sensitive), source, now, now),
            )
            memory = self._get_row(int(cur.lastrowid))
            conflicts = self._conflicts_for(memory)
        return AddResult(memory=memory, conflicts=conflicts)

    def update(
        self,
        memory_id: int,
        *,
        content: str | None = None,
        key: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        sensitive: bool | None = None,
    ) -> Memory:
        current = self.get(memory_id)
        if current is None:
            raise LSError(f"Não encontrei a memória {memory_id}.")
        new_content = current.content if content is None else content.strip()
        if not new_content:
            raise LSError("O conteúdo da memória não pode ficar vazio.")
        if _SECRET_RE.search(new_content):
            raise SecretRefused("Não guardo senhas, tokens ou chaves de API na memória.")
        new_category = current.category if category is None else self._check_category(category)
        new_key = current.key if key is None else key.strip()
        new_tags = ",".join(sorted(set(current.tags))) if tags is None else ",".join(sorted({t.strip().lower() for t in tags if t.strip()}))
        new_sensitive = current.sensitive if sensitive is None else bool(sensitive)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE memorias SET categoria=?, chave=?, conteudo=?, tags=?, sensivel=?, atualizado_em=? WHERE id=?",
                (new_category, new_key, new_content, new_tags, int(new_sensitive), _now(), memory_id),
            )
        updated = self.get(memory_id)
        assert updated is not None
        return updated

    def delete(self, memory_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM memorias WHERE id = ?", (memory_id,))
            return cur.rowcount > 0

    # Leitura -------------------------------------------------------------
    def get(self, memory_id: int) -> Memory | None:
        with self._lock:
            return self._get_row(memory_id)

    def list(self, *, category: str | None = None, limit: int = 200) -> list[Memory]:
        sql = "SELECT * FROM memorias"
        params: list[Any] = []
        if category:
            sql += " WHERE categoria = ?"
            params.append(category)
        sql += " ORDER BY atualizado_em DESC, id DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._to_memory(r) for r in rows]

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 10,
        include_sensitive: bool = False,
    ) -> list[Memory]:
        """Busca por palavras-chave com pontuação: chave > etiquetas > conteúdo."""
        candidates = self.list(category=category, limit=1000)
        if not include_sensitive:
            candidates = [m for m in candidates if not m.sensitive]
        phrase = normalize(query)
        terms = _tokens(query)
        if not phrase:
            return candidates[:limit]

        scored: list[tuple[float, Memory]] = []
        for memory in candidates:
            key_n, content_n = normalize(memory.key), normalize(memory.content)
            tags_n = " ".join(memory.tags)
            score = 0.0
            if key_n and (key_n in phrase or phrase in key_n):
                score += 6
            for term in terms:
                if term in key_n:
                    score += 3
                if term in tags_n:
                    score += 2
                if term in content_n:
                    score += 1
            if score > 0:
                scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [m for _, m in scored[:limit]]

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        """Memórias não sensíveis relevantes para o contexto de uma conversa."""
        return self.search(query, limit=limit, include_sensitive=False)

    def conflicts(self) -> list[tuple[Memory, Memory]]:
        """Pares de memórias com a mesma categoria e chave, mas conteúdos diferentes."""
        memories = self.list(limit=1000)
        pairs: list[tuple[Memory, Memory]] = []
        for i, a in enumerate(memories):
            if not a.key:
                continue
            for b in memories[i + 1 :]:
                if b.key and b.category == a.category and normalize(b.key) == normalize(a.key):
                    if normalize(a.content) != normalize(b.content):
                        pairs.append((a, b))
        return pairs

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT categoria, COUNT(*) AS n FROM memorias GROUP BY categoria").fetchall()
        return {r["categoria"]: r["n"] for r in rows}

    # Histórico de conversas ----------------------------------------------
    def log_message(self, role: str, text: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO mensagens (criado_em, papel, texto) VALUES (?, ?, ?)", (_now(), role, text))

    def recent_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, criado_em, papel, texto FROM mensagens ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        return [{"id": r["id"], "created_at": r["criado_em"], "role": r["papel"], "text": r["texto"]} for r in reversed(rows)]

    def clear_history(self) -> int:
        with self._lock, self._conn:
            return self._conn.execute("DELETE FROM mensagens").rowcount

    # Metadados -------------------------------------------------------------
    def meta_get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT valor FROM meta WHERE chave = ?", (key,)).fetchone()
        return row["valor"] if row else None

    def meta_set(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO meta (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (key, value),
            )

    def all_memories(self) -> list[Memory]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM memorias ORDER BY id").fetchall()
        return [self._to_memory(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # Internos --------------------------------------------------------------
    @staticmethod
    def _check_category(category: str) -> str:
        cat = normalize(category).replace(" ", "_") or "geral"
        if cat not in CATEGORIES:
            raise LSError(f"Categoria desconhecida '{category}'. Use uma de: {', '.join(CATEGORIES)}.")
        return cat

    def _get_row(self, memory_id: int) -> Memory | None:
        row = self._conn.execute("SELECT * FROM memorias WHERE id = ?", (memory_id,)).fetchone()
        return self._to_memory(row) if row else None

    def _conflicts_for(self, memory: Memory) -> list[Memory]:
        if not memory.key:
            return []
        rows = self._conn.execute(
            "SELECT * FROM memorias WHERE categoria = ? AND id != ?", (memory.category, memory.id)
        ).fetchall()
        same_key = [self._to_memory(r) for r in rows if normalize(r["chave"]) == normalize(memory.key)]
        return [m for m in same_key if normalize(m.content) != normalize(memory.content)]

    @staticmethod
    def _to_memory(row: sqlite3.Row) -> Memory:
        tags = tuple(t for t in row["tags"].split(",") if t)
        return Memory(
            id=row["id"],
            category=row["categoria"],
            key=row["chave"],
            content=row["conteudo"],
            tags=tags,
            sensitive=bool(row["sensivel"]),
            source=row["origem"],
            created_at=row["criado_em"],
            updated_at=row["atualizado_em"],
        )
