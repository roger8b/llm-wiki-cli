from __future__ import annotations

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import PageRepo
from llmwiki.services import index_service


def _write(brain: BrainPaths, rel: str, text: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TestReindex:
    def test_populates_pages_and_links(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/rag.md", "---\ntitle: RAG\ntype: concept\n---\n# RAG\n")
        _write(
            brain, "concepts/wiki.md",
            "---\ntitle: Wiki\ntype: concept\n---\n# Wiki\n[[RAG]]\n",
        )
        conn = get_connection(brain.db_path)
        try:
            report = index_service.reindex(brain, conn)
            pages = PageRepo(conn).list()
        finally:
            conn.close()
        assert report.pages_indexed == 2
        assert report.links_indexed == 1
        assert {p.title for p in pages} == {"RAG", "Wiki"}

    def test_skips_invalid_frontmatter(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/bad.md", "---\ntitle: : :\n  - x\n---\nbody")
        conn = get_connection(brain.db_path)
        try:
            report = index_service.reindex(brain, conn)
        finally:
            conn.close()
        assert "wiki/concepts/bad.md" in report.skipped

    def test_index_md_lists_pages_by_type(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/rag.md", "---\ntitle: RAG\ntype: concept\n---\n# RAG\n")
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)
            index_service.rebuild_index_md(brain, conn)
        finally:
            conn.close()
        content = brain.index_path.read_text(encoding="utf-8")
        assert "## concept" in content
        assert "[RAG](wiki/concepts/rag.md)" in content
