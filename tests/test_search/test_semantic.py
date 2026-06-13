"""Local semantic search: vector store, reindex embedding, degradation (#169).

The real vec0 path needs SQLite built with loadable-extension support; where
that is unavailable (e.g. some macOS python builds) the store-level tests skip,
but the degradation / disabled / wiring tests run everywhere.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import Page, PageType
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection, load_vec_extension
from llmwiki.db.repo import PageRepo
from llmwiki.search import factory as search_factory
from llmwiki.search.embeddings import build_embedder
from llmwiki.search.service import hybrid_search
from llmwiki.search.vector_store import SqliteVecStore
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


class FakeEmbedder:
    """Deterministic keyword-axis embedder: shared words → close vectors."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        t = text.lower()
        retrieval = any(w in t for w in ("rag", "retrieval", "context", "relevant"))
        vector = any(w in t for w in ("vector", "embedding"))
        markdown = any(w in t for w in ("markdown", "wiki", "knowledge"))
        v = [float(retrieval), float(vector), float(markdown)]
        return v if any(v) else [0.1, 0.1, 0.1]


def _seed_pages(brain: BrainPaths) -> None:
    (brain.wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (brain.wiki / "concepts" / "rag.md").write_text(
        "---\ntitle: RAG\ntype: concept\n---\n"
        "# RAG\nRetrieval augmented generation grounds an LLM in a vector store.\n",
        encoding="utf-8",
    )
    (brain.wiki / "concepts" / "wiki.md").write_text(
        "---\ntitle: Wiki\ntype: concept\n---\n# Wiki\nA knowledge base in markdown.\n",
        encoding="utf-8",
    )


def _cfg(brain: BrainPaths, model: str | None) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root, embedding_model=model)


class TestEmbedderWiring:
    def test_none_when_unset(self, brain: BrainPaths) -> None:
        assert build_embedder(_cfg(brain, None)) is None

    def test_none_for_unsupported_provider(self, brain: BrainPaths) -> None:
        assert build_embedder(_cfg(brain, "cohere:foo")) is None


class TestDisabled:
    def test_reindex_touches_no_embeddings(self, brain: BrainPaths) -> None:
        _seed_pages(brain)
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, _cfg(brain, None))
            n = conn.execute("SELECT COUNT(*) AS c FROM page_embeddings").fetchone()["c"]
        finally:
            conn.close()
        assert n == 0


class TestDegradation:
    def test_embed_failure_falls_back_to_fts(self, brain: BrainPaths) -> None:
        _seed_pages(brain)
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, _cfg(brain, None))

            class Boom:
                def embed(self, text: str) -> list[float]:
                    raise RuntimeError("provider offline")

            class Store:
                def query(self, vector, limit):  # never reached
                    return []

            # Must not raise; returns FTS results.
            hits = hybrid_search(conn, "markdown", embedder=Boom(), store=Store())
        finally:
            conn.close()
        assert any(h.path.endswith("wiki.md") for h in hits)


@needs_vec
class TestVectorStore:
    def test_replace_query_and_invalidate(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            for path, title in [("wiki/a.md", "A"), ("wiki/b.md", "B")]:
                PageRepo(conn).upsert(
                    Page(path=path, title=title, type=PageType.concept,
                         last_updated_at=datetime.now(UTC))
                )
            store = SqliteVecStore(conn)
            store.replace_page("wiki/a.md", [[1.0, 0.0, 0.0]], "h1")
            store.replace_page("wiki/b.md", [[0.0, 0.0, 1.0]], "h2")

            res = store.query([1.0, 0.0, 0.0], limit=2)
            assert res[0][0] == "wiki/a.md"
            assert store.page_hash("wiki/a.md") == "h1"
            assert store.indexed_paths() == {"wiki/a.md", "wiki/b.md"}

            store.delete_page("wiki/a.md")
            assert store.indexed_paths() == {"wiki/b.md"}
        finally:
            conn.close()


@needs_vec
class TestReindexEmbeddings:
    def _run(self, brain: BrainPaths, conn, monkeypatch) -> FakeEmbedder:
        emb = FakeEmbedder()
        monkeypatch.setattr(search_factory, "build_embedder", lambda cfg: emb)
        index_service.reindex(brain, conn, _cfg(brain, "ollama:fake"))
        return emb

    def test_populates_then_skips_unchanged(self, brain: BrainPaths, monkeypatch) -> None:
        _seed_pages(brain)
        conn = get_connection(brain.db_path)
        try:
            emb = self._run(brain, conn, monkeypatch)
            assert emb.calls == 2  # both pages embedded
            store = SqliteVecStore(conn)
            assert store.indexed_paths() == {"wiki/concepts/rag.md", "wiki/concepts/wiki.md"}

            emb.calls = 0
            index_service.reindex(brain, conn, _cfg(brain, "ollama:fake"))
            assert emb.calls == 0  # nothing changed → no re-embed (hash)
        finally:
            conn.close()

    def test_changed_page_reembedded(self, brain: BrainPaths, monkeypatch) -> None:
        _seed_pages(brain)
        conn = get_connection(brain.db_path)
        try:
            self._run(brain, conn, monkeypatch)
            (brain.wiki / "concepts" / "rag.md").write_text(
                "---\ntitle: RAG\ntype: concept\n---\n# RAG\nNew body about context.\n",
                encoding="utf-8",
            )
            emb = FakeEmbedder()
            monkeypatch.setattr(search_factory, "build_embedder", lambda cfg: emb)
            index_service.reindex(brain, conn, _cfg(brain, "ollama:fake"))
            assert emb.calls == 1  # only the changed page
        finally:
            conn.close()

    def test_removed_page_evicted(self, brain: BrainPaths, monkeypatch) -> None:
        _seed_pages(brain)
        conn = get_connection(brain.db_path)
        try:
            self._run(brain, conn, monkeypatch)
            (brain.wiki / "concepts" / "wiki.md").unlink()
            emb = FakeEmbedder()
            monkeypatch.setattr(search_factory, "build_embedder", lambda cfg: emb)
            index_service.reindex(brain, conn, _cfg(brain, "ollama:fake"))
            store = SqliteVecStore(conn)
            assert store.indexed_paths() == {"wiki/concepts/rag.md"}
        finally:
            conn.close()

    def test_semantic_query_finds_unkeyworded_page(
        self, brain: BrainPaths, monkeypatch
    ) -> None:
        _seed_pages(brain)
        conn = get_connection(brain.db_path)
        try:
            self._run(brain, conn, monkeypatch)
            emb = FakeEmbedder()
            store = SqliteVecStore(conn)
            # "how models find relevant context" shares no keyword with RAG body,
            # but is closest in vector space.
            hits = hybrid_search(
                conn, "how models find relevant context",
                embedder=emb, store=store, limit=5,
            )
            assert any(h.path.endswith("rag.md") for h in hits[:5])
        finally:
            conn.close()
