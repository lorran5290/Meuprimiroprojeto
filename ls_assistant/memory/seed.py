"""Memória inicial dos projetos já conhecidos.

Estes dados são um ponto de partida editável, não verdades fixas.
São gravados com origem 'seed' e aplicados apenas uma vez: se você apagar
ou alterar algum item, ele não volta na próxima inicialização.
"""

from __future__ import annotations

from ls_assistant.memory.store import MemoryStore

SEED_VERSION = "seed-v1"

SEED_MEMORIES: tuple[dict[str, object], ...] = (
    {
        "category": "projetos",
        "key": "ExNet Fiber",
        "content": "Provedor de internet por fibra óptica.",
        "tags": ("exnet", "fibra", "provedor"),
    },
    {
        "category": "projetos",
        "key": "ExNet Fiber",
        "content": "Projeto de landing page e site comercial.",
        "tags": ("exnet", "site", "landing page"),
    },
    {
        "category": "projetos",
        "key": "ExNet Fiber",
        "content": "Regiões de atendimento apresentadas inicialmente: Caju e Nova Iguaçu.",
        "tags": ("exnet", "regiao", "caju", "nova iguaçu"),
    },
    {
        "category": "projetos",
        "key": "ExNet Fiber",
        "content": "Identidade visual com azul-marinho, vermelho, índigo e dourado.",
        "tags": ("exnet", "identidade visual", "cores"),
    },
    {
        "category": "projetos",
        "key": "ExNet Fiber",
        "content": "Interesse em banners, imagens comerciais e apresentação de planos.",
        "tags": ("exnet", "banner", "planos"),
    },
    {
        "category": "projetos",
        "key": "DOM CULINÁRIO",
        "content": "Negócio de alimentação com cardápios e materiais de divulgação.",
        "tags": ("dom culinario", "alimentacao", "cardapio"),
    },
    {
        "category": "projetos",
        "key": "DOM CULINÁRIO",
        "content": "Instagram: @dom_culinario.",
        "tags": ("dom culinario", "instagram"),
    },
    {
        "category": "projetos",
        "key": "DOM CULINÁRIO",
        "content": "Perfil no iFood: Dom culinário.",
        "tags": ("dom culinario", "ifood"),
    },
    {
        "category": "projetos",
        "key": "DOM CULINÁRIO",
        "content": "Criação de cardápios, identidade visual e materiais para redes sociais.",
        "tags": ("dom culinario", "cardapio", "identidade visual", "redes sociais"),
    },
)


def apply_seed_memories(store: MemoryStore) -> int:
    """Grava a memória inicial uma única vez. Retorna quantos itens foram criados."""
    if store.meta_get("seed_applied") == SEED_VERSION:
        return 0
    created = 0
    for item in SEED_MEMORIES:
        store.add(
            str(item["content"]),
            category=str(item["category"]),
            key=str(item["key"]),
            tags=tuple(item["tags"]),  # type: ignore[arg-type]
            source="seed",
        )
        created += 1
    store.meta_set("seed_applied", SEED_VERSION)
    return created
