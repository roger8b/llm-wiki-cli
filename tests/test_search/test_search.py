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

    def test_merges_semantic(self, conn) -> None:
        class Emb:
            def embed(self, text: str) -> list[float]:
                return [1.0]

        class Store:
            def query(self, vector, limit):
                # devolve uma página com score alto que não casaria no FTS
                return [("wiki/concepts/rag.md", "RAG", 99.0)]

        hits = hybrid_search(conn, "markdown", embedder=Emb(), store=Store())
        # o resultado semântico de score alto deve vir primeiro
        assert hits[0].path.endswith("rag.md")
        assert hits[0].source == "semantic"
