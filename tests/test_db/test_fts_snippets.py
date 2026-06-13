"""FTS5 snippet support in PageFtsRepo.search_snippets (#171)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.db.connection import get_connection
from llmwiki.db.repo import PageFtsRepo
from llmwiki.search.service import keyword_search


@pytest.fixture
def fts(tmp_path: Path):
    c = get_connection(tmp_path / "db.sqlite")
    repo = PageFtsRepo(c)
    repo.add(
        "wiki/concepts/rag.md",
        "RAG",
        "Retrieval augmented generation grounds an LLM in a vector store of documents.",
        "[]",
    )
    repo.add(
        "wiki/concepts/wiki.md",
        "Wiki",
        "A wiki is a knowledge base written in markdown and linked together.",
        "[]",
    )
    yield repo
    c.close()


class TestSearchSnippets:
    def test_body_match_returns_highlighted_snippet(self, fts: PageFtsRepo) -> None:
        # "vector" is in the body, not the title.
        results = fts.search_snippets("vector", limit=5)
        assert results
        path, title, _rank, snippet = results[0]
        assert path.endswith("rag.md")
        assert snippet is not None
        assert "«vector»" in snippet

    def test_snippet_is_single_line(self, fts: PageFtsRepo) -> None:
        _, _, _, snippet = fts.search_snippets("markdown", limit=5)[0]
        assert snippet is not None
        assert "\n" not in snippet

    def test_search_still_returns_three_tuples(self, fts: PageFtsRepo) -> None:
        # Backwards-compatible API for callers that don't need snippets.
        results = fts.search("generation", limit=5)
        assert results and len(results[0]) == 3

    def test_keyword_search_populates_snippet(self, fts: PageFtsRepo) -> None:
        hits = keyword_search(fts.conn, "vector")
        assert hits and hits[0].snippet is not None
        assert "«vector»" in hits[0].snippet


class TestSearchToolFormat:
    def test_tool_includes_snippet_lines(self, brain) -> None:
        from llmwiki.core.config import WorkspaceConfig
        from llmwiki.db.repo import PageFtsRepo as Repo
        from llmwiki.llm_agents.tools import make_search_pages

        conn = get_connection(brain.db_path)
        try:
            Repo(conn).add(
                "wiki/concepts/rag.md",
                "RAG",
                "Retrieval augmented generation uses a vector store.",
                "[]",
            )
        finally:
            conn.close()
        out = make_search_pages(brain, WorkspaceConfig(brain_root=brain.root))("vector")
        lines = out.splitlines()
        # "path — title [source:score]" then an indented «snippet» (#170/#171).
        assert lines[0].startswith("wiki/concepts/rag.md — RAG [keyword:")
        assert lines[1].strip().startswith("«") and "«vector»" in lines[1]

    def test_tool_no_results(self, brain) -> None:
        from llmwiki.core.config import WorkspaceConfig
        from llmwiki.llm_agents.tools import make_search_pages

        search = make_search_pages(brain, WorkspaceConfig(brain_root=brain.root))
        assert search("nonexistentterm") == "Nenhuma página encontrada."
