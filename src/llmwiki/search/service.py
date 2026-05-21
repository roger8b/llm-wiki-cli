"""Search service: busca textual (FTS5) com hook opcional de busca semântica.

A busca por keyword (FTS5) é real e sempre disponível. A camada semântica é um
ponto de extensão: forneça um ``EmbeddingProvider`` + ``VectorStore`` para ativar
busca híbrida (ex.: Qdrant). Sem provider, cai para FTS puro.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..db.repo import PageFtsRepo


@dataclass
class SearchHit:
    path: str
    title: str
    score: float
    source: str  # "keyword" | "semantic"


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


@runtime_checkable
class VectorStore(Protocol):
    def query(self, vector: list[float], limit: int) -> list[tuple[str, str, float]]: ...


def keyword_search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchHit]:
    return [
        SearchHit(path=p, title=t, score=-rank, source="keyword")
        for p, t, rank in PageFtsRepo(conn).search(query, limit)
    ]


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    embedder: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
) -> list[SearchHit]:
    """Combina keyword (FTS) e semântico (se embedder+store fornecidos).

    Faz fusão por path mantendo o melhor score de cada origem. Sem camada
    semântica configurada, retorna apenas os resultados de keyword.
    """
    hits: dict[str, SearchHit] = {}
    for hit in keyword_search(conn, query, limit):
        hits[hit.path] = hit

    if embedder is not None and store is not None:
        vector = embedder.embed(query)
        for path, title, score in store.query(vector, limit):
            existing = hits.get(path)
            if existing is None or score > existing.score:
                hits[path] = SearchHit(path=path, title=title, score=score, source="semantic")

    return sorted(hits.values(), key=lambda h: h.score, reverse=True)[:limit]
