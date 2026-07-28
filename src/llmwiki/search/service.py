"""Search service: text search (FTS5) with optional semantic search hook.

Keyword search (FTS5) is real and always available. The semantic layer is an
extension point: provide an ``EmbeddingProvider`` + ``VectorStore`` to enable
hybrid search (e.g. Qdrant). Without a provider, it falls back to pure FTS.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..db.repo import PageFtsRepo

logger = logging.getLogger("llmwiki.search.service")


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
    # Rows are (path, title, score) or (path, title, score, passage) (#354);
    # consumers index positionally and treat len > 3 as carrying a passage.
    def query(self, vector: list[float], limit: int) -> Sequence[tuple[Any, ...]]: ...


def keyword_search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchHit]:
    return [
        SearchHit(path=p, title=t, score=-rank, source="keyword", snippet=snippet)
        for p, t, rank, snippet in PageFtsRepo(conn).search_snippets(query, limit)
    ]


# Reciprocal Rank Fusion constant (#169). 60 is the value from the original RRF
# paper; it damps the contribution of low-ranked items from either list.
_RRF_K = 60


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    embedder: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
    expander: Callable[[str], list[str]] | None = None,
) -> list[SearchHit]:
    """Fuse keyword (FTS) and semantic (when configured) results via RRF.

    Reciprocal Rank Fusion combines the two ranked lists by rank, not raw score,
    so incomparable FTS bm25 and vector distances merge sanely. ``source`` marks
    the list where the page ranked best. A runtime embedding failure (e.g. the
    provider is offline) degrades to pure FTS — search never breaks because of
    the semantic layer. Without a configured layer, returns keyword results.
    """
    queries = [query]
    if expander is not None:
        # Multi-query expansion (#355): every variant contributes a keyword and
        # a semantic list to the same RRF. Generator failure = original only.
        try:
            queries = list(dict.fromkeys(expander(query))) or [query]
        except Exception as exc:  # noqa: BLE001
            logger.warning("query expansion failed, using original query: %s", exc)

    keyword = keyword_search(conn, query, limit)
    snippets = {hit.path: hit.snippet for hit in keyword if hit.snippet}
    extra_keyword: list[list[SearchHit]] = [
        keyword_search(conn, q, limit) for q in queries[1:]
    ]

    semantic: list[tuple[str, str]] = []  # (path, title), already ranked
    extra_semantic: list[list[tuple[str, str]]] = []
    if embedder is not None and store is not None:
        try:
            for q in queries[1:]:
                rows = store.query(embedder.embed(q), limit)
                extra_semantic.append([(r[0], r[1]) for r in rows])
            vector = embedder.embed(query)
            for row in store.query(vector, limit):
                # 4-tuples carry the winning chunk's passage (#354); legacy
                # 3-tuple stores keep working without one.
                path, title = row[0], row[1]
                semantic.append((path, title))
                if len(row) > 3 and row[3]:
                    snippets.setdefault(path, row[3])
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic search failed, using FTS only: %s", exc)

    scores: dict[str, float] = {}
    meta: dict[str, tuple[str, str, int]] = {}  # path -> (title, source, best_rank)

    def fuse(path: str, title: str, rank: int, source: str) -> None:
        scores[path] = scores.get(path, 0.0) + 1.0 / (_RRF_K + rank)
        prev = meta.get(path)
        if prev is None or rank < prev[2]:
            meta[path] = (title or (prev[0] if prev else path), source, rank)
        elif prev[0] == path and title:
            meta[path] = (title, prev[1], prev[2])

    for rank, hit in enumerate(keyword):
        fuse(hit.path, hit.title, rank, "keyword")
    for rank, (path, title) in enumerate(semantic):
        fuse(path, title, rank, "semantic")
    for hits_k in extra_keyword:
        for rank, hit in enumerate(hits_k):
            fuse(hit.path, hit.title, rank, "keyword")
    for sem in extra_semantic:
        for rank, (path, title) in enumerate(sem):
            fuse(path, title, rank, "semantic")

    hits = [
        SearchHit(
            path=path,
            title=meta[path][0],
            score=score,
            source=meta[path][1],
            snippet=snippets.get(path),
        )
        for path, score in scores.items()
    ]
    return sorted(hits, key=lambda h: h.score, reverse=True)[:limit]
