"""Local semantic search: vector store, reindex embedding, degradation (#169).

The real vec0 path needs SQLite built with loadable-extension support; where
that is unavailable (e.g. some macOS python builds) the store-level tests skip,
but the degradation / disabled / wiring tests run everywhere.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import FileChange, Page, PageType
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection, load_vec_extension
from llmwiki.db.repo import PageRepo
from llmwiki.search import factory as search_factory
from llmwiki.search.embeddings import build_embedder
from llmwiki.search.service import hybrid_search
from llmwiki.search.vector_store import SqliteVecStore
from llmwiki.services import change_request_service, index_service


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


class FakeStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def page_hash(self, path: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM page_embeddings WHERE path=? AND chunk_idx=0",
            (path,),
        ).fetchone()
        return row["content_hash"] if row else None

    def indexed_paths(self) -> set[str]:
        rows = self.conn.execute("SELECT DISTINCT path FROM page_embeddings").fetchall()
        return {r["path"] for r in rows}

    def delete_page(self, path: str) -> None:
        self.conn.execute("DELETE FROM page_embeddings WHERE path=?", (path,))
        self.conn.commit()

    def replace_page(
        self,
        path: str,
        vectors: list[list[float]],
        content_hash: str,
        chunks: list[str] | None = None,
    ) -> None:
        self.delete_page(path)
        for idx, _ in enumerate(vectors):
            self.conn.execute(
                "INSERT INTO page_embeddings (path, chunk_idx, content_hash) VALUES (?, ?, ?)",
                (path, idx, content_hash),
            )
        self.conn.commit()


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


def _write_embedding_config(wiki_home: Path) -> None:
    (wiki_home / "config.yaml").write_text("embedding_model: ollama:fake\n", encoding="utf-8")


def _patch_fake_semantic(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    emb = FakeEmbedder()

    def build_backend(cfg: WorkspaceConfig, conn: sqlite3.Connection):
        return (emb, FakeStore(conn)) if cfg.embedding_model else (None, None)

    monkeypatch.setattr(search_factory, "build_semantic_backend", build_backend)
    return emb


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


class TestReindexConfig:
    def test_cfg_none_loads_config_logs_and_skips_unchanged(
        self,
        brain: BrainPaths,
        isolated_wiki_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _seed_pages(brain)
        _write_embedding_config(isolated_wiki_home)
        emb = _patch_fake_semantic(monkeypatch)
        conn = get_connection(brain.db_path)
        try:
            with caplog.at_level(logging.INFO, logger="llmwiki.services.index"):
                report = index_service.reindex(brain, conn)
            assert emb.calls == 2
            assert report.embeddings_indexed == 2
            assert "semantic embeddings: built=2 skipped=0 failed=0" in caplog.text

            emb.calls = 0
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="llmwiki.services.index"):
                report = index_service.reindex(brain, conn)
            assert emb.calls == 0
            assert report.embeddings_skipped == 2
            assert "semantic embeddings: built=0 skipped=2 failed=0" in caplog.text
        finally:
            conn.close()

    def test_cr_apply_builds_embeddings_from_global_config(
        self,
        brain: BrainPaths,
        isolated_wiki_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write_embedding_config(isolated_wiki_home)
        emb = _patch_fake_semantic(monkeypatch)
        conn = get_connection(brain.db_path)
        try:
            cr = change_request_service.create_from_changes(
                [
                    FileChange(
                        path="wiki/concepts/rag.md",
                        operation="create",
                        diff="",
                        new_content="---\ntitle: RAG\ntype: concept\n---\n# RAG\nretrieval\n",
                    )
                ],
                "add rag",
                brain,
                conn,
            )
            change_request_service.apply(cr.id, brain, conn)
            n = conn.execute("SELECT COUNT(*) AS c FROM page_embeddings").fetchone()["c"]
        finally:
            conn.close()
        assert emb.calls == 1
        assert n > 0

    def test_cli_index_passes_loaded_config(
        self,
        brain: BrainPaths,
        isolated_wiki_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from llmwiki.interfaces.cli.commands import wiki as wiki_cmd

        _seed_pages(brain)
        _write_embedding_config(isolated_wiki_home)
        emb = _patch_fake_semantic(monkeypatch)
        monkeypatch.setattr(wiki_cmd, "load_active_brain", lambda: brain)

        wiki_cmd.index()

        assert emb.calls == 2

    def test_graph_endpoint_reindexes_with_global_config(
        self,
        brain: BrainPaths,
        isolated_wiki_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from llmwiki.interfaces.api.routers import search as search_router

        _seed_pages(brain)
        _write_embedding_config(isolated_wiki_home)
        emb = _patch_fake_semantic(monkeypatch)
        monkeypatch.setattr(search_router, "_ctx", lambda: brain)

        out = search_router.graph()

        assert emb.calls == 2
        assert len(out["nodes"]) == 2

    def test_failed_reembed_deletes_stale_vectors(
        self,
        brain: BrainPaths,
        isolated_wiki_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_pages(brain)
        _write_embedding_config(isolated_wiki_home)
        _patch_fake_semantic(monkeypatch)
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)
            assert FakeStore(conn).indexed_paths() == {
                "wiki/concepts/rag.md",
                "wiki/concepts/wiki.md",
            }
            # rag.md changes but the embedder now fails: stale vectors must go.
            (brain.wiki / "concepts" / "rag.md").write_text(
                "---\ntitle: RAG\ntype: concept\n---\n# RAG\nchanged body.\n",
                encoding="utf-8",
            )

            class Boom:
                def embed(self, text: str) -> list[float]:
                    raise RuntimeError("provider offline")

            def build_backend(cfg: WorkspaceConfig, conn: sqlite3.Connection):
                return (Boom(), FakeStore(conn)) if cfg.embedding_model else (None, None)

            monkeypatch.setattr(search_factory, "build_semantic_backend", build_backend)
            report = index_service.reindex(brain, conn)
            assert report.embeddings_failed == 1
            # wiki.md unchanged (kept); rag.md's stale vectors evicted.
            assert FakeStore(conn).indexed_paths() == {"wiki/concepts/wiki.md"}
        finally:
            conn.close()


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
