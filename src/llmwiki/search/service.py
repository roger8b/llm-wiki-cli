"""Search service: text search (FTS5) with optional semantic search hook.

Keyword search (FTS5) is real and always available. The semantic layer is an
extension point: provide an ``EmbeddingProvider`` + ``VectorStore`` to enable
hybrid search (e.g. Qdrant). Without a provider, it falls back to pure FTS.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

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
    def query(self, vector: list[float], limit: int) -> list[tuple[str, str, float]]: ...


def keyword_search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchHit]:
    return [
        SearchHit(path=p, title=t, score=-rank, source="keyword", snippet=snippet)
        for p, t, rank, snippet in PageFtsRepo(conn).search_snippets(query, limit)
    ]


# Reciprocal Rank Fusion constant (#169). 60 is the value from the original RRF
# paper; it damps the contribution of low-ranked items from either list.
_RRF_K = 60


def _graph_degrees(conn: sqlite3.Connection) -> dict[str, int]:
    """Incoming-link count per slugified wikilink target (#353).

    ``links.to_page`` stores the wikilink TITLE, so candidates are matched by
    slug (title or path stem). One aggregated query — no per-hit lookups.
    """
    from ..core.markdown import slugify

    rows = conn.execute("SELECT to_page, COUNT(*) AS n FROM links GROUP BY to_page").fetchall()
    degrees: dict[str, int] = {}
    for r in rows:
        slug = slugify(r["to_page"])
        if slug:
            degrees[slug] = degrees.get(slug, 0) + int(r["n"])
    return degrees


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    embedder: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
    graph_signal: bool = False,
) -> list[SearchHit]:
    """Fuse keyword (FTS) and semantic (when configured) results via RRF.

    Reciprocal Rank Fusion combines the two ranked lists by rank, not raw score,
    so incomparable FTS bm25 and vector distances merge sanely. ``source`` marks
    the list where the page ranked best. A runtime embedding failure (e.g. the
    provider is offline) degrades to pure FTS — search never breaks because of
    the semantic layer. Without a configured layer, returns keyword results.
    """
    keyword = keyword_search(conn, query, limit)
    snippets = {hit.path: hit.snippet for hit in keyword if hit.snippet}

    semantic: list[tuple[str, str]] = []  # (path, title), already ranked
    if embedder is not None and store is not None:
        try:
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

    if graph_signal and scores:
        # Third list (#353): the candidates already matched, ordered by
        # backlink degree. A prior, not a matcher — only boosts scores; it
        # never introduces pages and never changes a hit's ``source`` label.
        from pathlib import PurePosixPath

        from ..core.markdown import slugify

        degrees = _graph_degrees(conn)

        def degree_of(path: str) -> int:
            title_slug = slugify(meta[path][0]) if path in meta else ""
            stem_slug = slugify(PurePosixPath(path).stem)
            return max(degrees.get(title_slug, 0), degrees.get(stem_slug, 0))

        ranked = sorted(
            (p for p in scores if degree_of(p) > 0), key=lambda p: -degree_of(p)
        )
        for rank, path in enumerate(ranked):
            scores[path] += 1.0 / (_RRF_K + rank)

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
