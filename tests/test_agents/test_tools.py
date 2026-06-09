"""Tests for domain tools exposed to agents (epic #122)."""

from __future__ import annotations

from llmwiki.agents.tools import make_search_pages
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import index_service


def _add_page(brain: BrainPaths, rel: str, title: str, body: str) -> None:
    page = brain.wiki / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        f"---\ntitle: {title}\ntype: concept\n---\n# {title}\n{body}\n", encoding="utf-8"
    )


class TestSearchPages:
    def test_finds_indexed_page(self, brain: BrainPaths) -> None:
        _add_page(brain, "concepts/rag.md", "RAG", "retrieval augmented generation")
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)
        finally:
            conn.close()
        search = make_search_pages(brain)
        out = search("retrieval")
        assert "wiki/concepts/rag.md" in out
        assert "RAG" in out

    def test_returns_message_when_empty(self, brain: BrainPaths) -> None:
        search = make_search_pages(brain)
        out = search("nonexistent-term-xyz")
        assert "Nenhuma página encontrada" in out
