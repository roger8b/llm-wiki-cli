"""Tag index: reindex populates page_tags; counts + filter (#189)."""

from __future__ import annotations

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import PageRepo, TagRepo
from llmwiki.services import index_service


def _page(brain: BrainPaths, rel: str, title: str, tags: list[str]) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    tag_yaml = "[" + ", ".join(tags) + "]"
    p.write_text(
        f"---\ntitle: {title}\ntype: concept\ntags: {tag_yaml}\n---\n# {title}\nbody\n",
        encoding="utf-8",
    )


def test_reindex_populates_and_counts(brain: BrainPaths) -> None:
    _page(brain, "concepts/a.md", "A", ["RAG", "ai"])
    _page(brain, "concepts/b.md", "B", ["rag", "ml"])  # different casing of RAG
    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn)
        counts = dict(TagRepo(conn).counts())
    finally:
        conn.close()
    # RAG/rag collapse to one normalised tag with count 2.
    assert counts["rag"] == 2
    assert counts["ai"] == 1
    assert counts["ml"] == 1


def test_by_tag_filters(brain: BrainPaths) -> None:
    _page(brain, "concepts/a.md", "A", ["rag"])
    _page(brain, "concepts/b.md", "B", ["ml"])
    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn)
        rag_pages = [p.path for p in PageRepo(conn).by_tag("RAG")]  # case-insensitive
    finally:
        conn.close()
    assert rag_pages == ["wiki/concepts/a.md"]


def test_reindex_refreshes_counts(brain: BrainPaths) -> None:
    _page(brain, "concepts/a.md", "A", ["rag"])
    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn)
        assert dict(TagRepo(conn).counts()) == {"rag": 1}
        # Remove the tag and reindex → count updates.
        _page(brain, "concepts/a.md", "A", ["ml"])
        index_service.reindex(brain, conn)
        counts = dict(TagRepo(conn).counts())
    finally:
        conn.close()
    assert "rag" not in counts and counts["ml"] == 1
