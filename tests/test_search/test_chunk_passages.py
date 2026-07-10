"""Tests for chunk-level passages in semantic search (#354, epic #348).

The vec store keeps a short excerpt (``chunk_text``) of each embedded chunk;
``query`` returns the winning chunk's passage per page and ``hybrid_search``
uses it as the snippet when FTS has none. Old 3-tuple stores keep working.
"""

from __future__ import annotations

import pytest

from llmwiki.db.connection import get_connection
from llmwiki.search.service import hybrid_search
from llmwiki.search.vector_store import SqliteVecStore


@pytest.fixture
def conn(tmp_path):
    conn = get_connection(tmp_path / "meta.db")
    yield conn
    conn.close()


class OneVecEmbedder:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


def test_migration_adds_chunk_text_column(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(page_embeddings)")}
    assert "chunk_text" in cols


def test_replace_page_stores_passage_and_query_returns_it(conn):
    store = SqliteVecStore(conn)
    if not store.available:
        pytest.skip("sqlite-vec unavailable")
    long_chunk = "Trecho relevante sobre grafos. " * 30  # > cap
    store.replace_page("wiki/concepts/g.md", [[1.0, 0.0]], "h1", chunks=[long_chunk])
    rows = store.query([1.0, 0.0], limit=5)
    assert rows and rows[0][0] == "wiki/concepts/g.md"
    passage = rows[0][3]
    assert passage and passage.startswith("Trecho relevante")
    assert len(passage) <= 300  # cap at storage


def test_replace_page_without_chunks_keeps_working(conn):
    """Pre-migration behaviour: no chunk texts -> passage is None."""
    store = SqliteVecStore(conn)
    if not store.available:
        pytest.skip("sqlite-vec unavailable")
    store.replace_page("wiki/concepts/g.md", [[1.0, 0.0]], "h1")
    rows = store.query([1.0, 0.0], limit=5)
    assert rows[0][3] is None


def test_hybrid_uses_semantic_passage_when_fts_has_no_snippet(conn):
    """A purely semantic hit carries the chunk passage as its snippet."""
    store = SqliteVecStore(conn)
    if not store.available:
        pytest.skip("sqlite-vec unavailable")
    conn.execute(
        "INSERT INTO wiki_pages (path, title, type, tags, confidence, last_updated_at,"
        " source_count) VALUES ('wiki/concepts/g.md', 'Grafos', 'concept', '[]', NULL,"
        " '2026-01-01', 0)"
    )
    store.replace_page("wiki/concepts/g.md", [[1.0, 0.0]], "h1", chunks=["Trecho sobre grafos."])
    hits = hybrid_search(conn, "zzz-sem-match-fts", embedder=OneVecEmbedder(), store=store)
    hit = next(h for h in hits if h.path == "wiki/concepts/g.md")
    assert hit.source == "semantic"
    assert hit.snippet == "Trecho sobre grafos."


def test_hybrid_accepts_legacy_3tuple_stores(conn):
    """Regression-safe: stores returning (path, title, score) still work."""

    class Legacy:
        def query(self, vector, limit):
            return [("wiki/concepts/x.md", "X", -0.5)]

    hits = hybrid_search(conn, "zzz", embedder=OneVecEmbedder(), store=Legacy())
    assert [h.path for h in hits] == ["wiki/concepts/x.md"]
    assert hits[0].snippet is None
