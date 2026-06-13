"""search_pages / related_pages over hybrid search (#170)."""

from __future__ import annotations

import sqlite3

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection, load_vec_extension
from llmwiki.llm_agents.tools import make_search_pages
from llmwiki.search import factory as search_factory
from llmwiki.services import index_service


def _vec_available() -> bool:
    conn = sqlite3.connect(":memory:")
    try:
        return load_vec_extension(conn)
    finally:
        conn.close()


needs_vec = pytest.mark.skipif(
    not _vec_available(), reason="SQLite without loadable sqlite-vec extension"
)


def _add(brain: BrainPaths, rel: str, title: str, body: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: {title}\ntype: concept\n---\n# {title}\n{body}\n", encoding="utf-8")


def _reindex(brain: BrainPaths, cfg: WorkspaceConfig) -> None:
    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn, cfg)
    finally:
        conn.close()


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        t = text.lower()
        return [
            float(any(w in t for w in ("rag", "retrieval", "context", "relevant"))),
            float(any(w in t for w in ("vector", "embedding"))),
            float(any(w in t for w in ("markdown", "wiki", "knowledge"))),
        ] or [0.1, 0.1, 0.1]


class TestKeywordOnly:
    def test_output_format_has_source_and_score(self, brain: BrainPaths) -> None:
        cfg = WorkspaceConfig(brain_root=brain.root)  # no embedding_model → FTS
        _add(brain, "concepts/rag.md", "RAG", "retrieval augmented generation")
        _reindex(brain, cfg)
        out = make_search_pages(brain, cfg)("retrieval")
        assert "wiki/concepts/rag.md — RAG [keyword:" in out


@needs_vec
class TestSemantic:
    def test_finds_semantic_only_hit(self, brain: BrainPaths, monkeypatch) -> None:
        cfg = WorkspaceConfig(brain_root=brain.root, embedding_model="ollama:fake")
        monkeypatch.setattr(search_factory, "build_embedder", lambda c: FakeEmbedder())
        _add(brain, "concepts/rag.md", "RAG",
             "retrieval augmented generation grounds an llm in a vector store")
        _add(brain, "concepts/wiki.md", "Wiki", "a knowledge base in markdown")
        _reindex(brain, cfg)
        # No lexical overlap with the RAG body, but closest in vector space.
        out = make_search_pages(brain, cfg)("how models find relevant context")
        assert "rag.md" in out
        assert "[semantic:" in out
