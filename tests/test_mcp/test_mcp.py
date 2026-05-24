from __future__ import annotations

import pytest

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.interfaces.mcp import server


@pytest.fixture
def seeded(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    p = brain.wiki / "concepts" / "rag.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: RAG\ntype: concept\n---\n# RAG\nretrieval\n", encoding="utf-8")
    from llmwiki.services import index_service

    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn)
    finally:
        conn.close()
    return brain


class TestMcpHelpers:
    def test_search(self, seeded) -> None:
        assert "rag.md" in server._search("retrieval")

    def test_get_page(self, seeded) -> None:
        assert "# RAG" in server._get_page("wiki/concepts/rag.md")

    def test_get_missing_page(self, seeded) -> None:
        assert "not found" in server._get_page("wiki/concepts/nope.md")

    def test_lint(self, seeded) -> None:
        out = server._lint()
        assert isinstance(out, str)

    def test_pending_changes_empty(self, seeded) -> None:
        assert "No pending" in server._list_pending()


class TestBuildServer:
    def test_registers_tools(self, seeded) -> None:
        mcp = server.build_server()
        assert mcp is not None
