"""Tests for domain tools exposed to agents (epic #122)."""

from __future__ import annotations

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import LinkRepo
from llmwiki.llm_agents.tools import (
    make_get_backlinks,
    make_read_metadata,
    make_search_by_type,
    make_search_pages,
    wiki_stats,
)
from llmwiki.services import index_service


def _add_page(
    brain: BrainPaths, rel: str, title: str, body: str, ptype: str = "concept"
) -> None:
    page = brain.wiki / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        f"---\ntitle: {title}\ntype: {ptype}\n---\n# {title}\n{body}\n", encoding="utf-8"
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


class TestSearchByType:
    def test_lists_pages_of_type(self, brain: BrainPaths) -> None:
        _add_page(brain, "concepts/rag.md", "RAG", "body")
        _add_page(brain, "decisions/d1.md", "D1", "body", ptype="decision")
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)
        finally:
            conn.close()
        out = make_search_by_type(brain)("concept")
        assert "wiki/concepts/rag.md" in out
        assert "wiki/decisions/d1.md" not in out

    def test_empty_type(self, brain: BrainPaths) -> None:
        out = make_search_by_type(brain)("research")
        assert "Nenhuma página do tipo 'research'" in out


class TestWikiStats:
    def test_empty_wiki(self, brain: BrainPaths) -> None:
        assert "wiki vazia" in wiki_stats(brain)

    def test_counts_by_type(self, brain: BrainPaths) -> None:
        _add_page(brain, "concepts/rag.md", "RAG", "body")
        _add_page(brain, "concepts/emb.md", "Embeddings", "body")
        _add_page(brain, "entities/google.md", "Google", "body", ptype="entity")
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)
        finally:
            conn.close()
        out = wiki_stats(brain)
        assert "3 páginas" in out
        assert "concept: 2" in out
        assert "entity: 1" in out


class TestGetBacklinks:
    def test_lists_incoming(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            LinkRepo(conn).add("wiki/concepts/a.md", "wiki/concepts/rag.md")
            LinkRepo(conn).add("wiki/concepts/b.md", "wiki/concepts/rag.md")
        finally:
            conn.close()
        out = make_get_backlinks(brain)("wiki/concepts/rag.md")
        assert "wiki/concepts/a.md" in out
        assert "wiki/concepts/b.md" in out

    def test_no_backlinks(self, brain: BrainPaths) -> None:
        out = make_get_backlinks(brain)("wiki/concepts/orphan.md")
        assert "Nenhuma página aponta" in out


class TestReadMetadata:
    def test_reads_frontmatter_only(self, brain: BrainPaths) -> None:
        _add_page(brain, "concepts/rag.md", "RAG", "long body here")
        out = make_read_metadata(brain)("wiki/concepts/rag.md")
        assert "title: RAG" in out
        assert "type: concept" in out
        assert "long body here" not in out

    def test_missing_file(self, brain: BrainPaths) -> None:
        out = make_read_metadata(brain)("wiki/concepts/nope.md")
        assert "não encontrado" in out
