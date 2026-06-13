from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.db.connection import get_connection
from llmwiki.db.repo import PageFtsRepo
from llmwiki.search.service import hybrid_search, keyword_search


@pytest.fixture
def conn(tmp_path: Path):
    c = get_connection(tmp_path / "db.sqlite")
    fts = PageFtsRepo(c)
    fts.add("wiki/concepts/rag.md", "RAG", "retrieval augmented generation", "[]")
    fts.add("wiki/concepts/wiki.md", "Wiki", "knowledge base markdown", "[]")
    yield c
    c.close()


class TestKeyword:
    def test_finds_match(self, conn) -> None:
        hits = keyword_search(conn, "retrieval")
        assert hits and hits[0].path.endswith("rag.md")
        assert hits[0].source == "keyword"


class TestHybrid:
    def test_fts_only_without_provider(self, conn) -> None:
        hits = hybrid_search(conn, "markdown")
        assert any(h.path.endswith("wiki.md") for h in hits)

    def test_merges_semantic_recall(self, conn) -> None:
        # RRF fuses by RANK: a page only the semantic layer finds still appears
        # in the results (recall), tagged as its dominant source.
        class Emb:
            def embed(self, text: str) -> list[float]:
                return [1.0]

        class Store:
            def query(self, vector, limit):
                # rag.md would NOT match the keyword "markdown".
                return [("wiki/concepts/rag.md", "RAG", -0.1)]

        hits = hybrid_search(conn, "markdown", embedder=Emb(), store=Store())
        by_path = {h.path: h for h in hits}
        assert any(p.endswith("rag.md") for p in by_path)
        assert by_path["wiki/concepts/rag.md"].source == "semantic"

    def test_rrf_ranks_pages_in_both_lists_first(self, conn) -> None:
        # A page that ranks in BOTH the keyword and semantic lists accumulates
        # RRF score from both and beats a single-list page.
        class Emb:
            def embed(self, text: str) -> list[float]:
                return [1.0]

        class Store:
            def query(self, vector, limit):
                return [
                    ("wiki/concepts/wiki.md", "Wiki", -0.1),  # also a keyword hit
                    ("wiki/concepts/rag.md", "RAG", -0.2),
                ]

        hits = hybrid_search(conn, "markdown", embedder=Emb(), store=Store())
        assert hits[0].path.endswith("wiki.md")  # present in both lists → top
