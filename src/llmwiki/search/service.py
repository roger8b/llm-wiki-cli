"""Search service: text search (FTS5) with optional semantic search hook.

Keyword search (FTS5) is real and always available. The semantic layer is an
extension point: provide an ``EmbeddingProvider`` + ``VectorStore`` to enable
hybrid search (e.g. Qdrant). Without a provider, it falls back to pure FTS.
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
    snippet: str | None = None  # FTS5 highlight excerpt (#171); None if unavailable


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


@runtime_checkable
class VectorStore(Protocol):
    def query(self, vector: list[float], limit: int) -> list[tuple[str, str, float]]: ...


def keyword_search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchHit]:
    return [
        SearchHit(path=p, title=t, score=-rank, source="keyword", snippet=snippet)
        for p, t, rank, snippet in PageFtsRepo(conn).search_snippets(query, limit)
    ]


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    embedder: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
) -> list[SearchHit]:
    """Combines keyword (FTS) and semantic (if embedder+store are provided).

    Merges by path, keeping the best score from each source. Without a configured
    semantic layer, returns keyword results only.
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
