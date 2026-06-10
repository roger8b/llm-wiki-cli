"""Tests for ingestion integrity & dedup (epic #120).

- dedup by content hash before the LLM call (#134)
- cross-check of declared vs written pages (#133)
- category/confidence propagation to FileChange (#135)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.errors import SourceAlreadyProcessedError
from llmwiki.core.misc import sha256
from llmwiki.core.models import Source, SourceStatus
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import SourceRepo
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import ingest_service


def _runner_writes_rag(cfg, backend: ChangeRequestBackend, *, source_path, source_text):
    backend.write(
        "wiki/concepts/rag.md",
        "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n# RAG\nBody.\n",
    )
    return IngestionResult(summary="Created RAG", new_pages=["wiki/concepts/rag.md"])


def _make_source(brain: BrainPaths, text: str = "about rag") -> Path:
    src = brain.raw / "articles" / "art.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(text, encoding="utf-8")
    return src


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


class TestDedup:
    def test_skips_when_already_processed(self, brain: BrainPaths) -> None:
        src = _make_source(brain)
        digest = sha256(src.read_bytes())
        conn = get_connection(brain.db_path)
        try:
            # Register the source as already processed.
            SourceRepo(conn).upsert(
                Source(
                    path=brain.relative(src),
                    type="md",
                    hash=digest,
                    added_at=datetime.now(UTC),
                    status=SourceStatus.processed,
                )
            )
            calls = {"n": 0}

            def counting_runner(cfg, backend, *, source_path, source_text):
                calls["n"] += 1
                return _runner_writes_rag(
                    cfg, backend, source_path=source_path, source_text=source_text
                )

            with pytest.raises(SourceAlreadyProcessedError):
                ingest_service.ingest(src, brain, conn, _cfg(brain), runner=counting_runner)
            assert calls["n"] == 0  # LLM never invoked
        finally:
            conn.close()

    def test_force_overrides_dedup(self, brain: BrainPaths) -> None:
        src = _make_source(brain)
        digest = sha256(src.read_bytes())
        conn = get_connection(brain.db_path)
        try:
            SourceRepo(conn).upsert(
                Source(
                    path=brain.relative(src),
                    type="md",
                    hash=digest,
                    added_at=datetime.now(UTC),
                    status=SourceStatus.processed,
                )
            )
            cr = ingest_service.ingest(
                src, brain, conn, _cfg(brain), runner=_runner_writes_rag, force=True
            )
            assert cr.files_changed == 1
        finally:
            conn.close()

    def test_pending_source_is_not_skipped(self, brain: BrainPaths) -> None:
        src = _make_source(brain)
        digest = sha256(src.read_bytes())
        conn = get_connection(brain.db_path)
        try:
            SourceRepo(conn).upsert(
                Source(
                    path=brain.relative(src),
                    type="md",
                    hash=digest,
                    added_at=datetime.now(UTC),
                    status=SourceStatus.pending,
                )
            )
            cr = ingest_service.ingest(src, brain, conn, _cfg(brain), runner=_runner_writes_rag)
            assert cr.files_changed == 1
        finally:
            conn.close()


class TestCrossCheck:
    def test_phantom_result_warns(
        self, brain: BrainPaths, caplog: pytest.LogCaptureFixture
    ) -> None:
        """LLM declares pages but writes nothing → warning, empty CR."""

        def liar(cfg, backend, *, source_path, source_text):
            return IngestionResult(summary="lied", new_pages=["wiki/concepts/ghost.md"])

        src = _make_source(brain)
        conn = get_connection(brain.db_path)
        try:
            with caplog.at_level(logging.WARNING, logger="llmwiki.services.ingest"):
                cr = ingest_service.ingest(src, brain, conn, _cfg(brain), runner=liar)
        finally:
            conn.close()
        assert cr.files_changed == 0
        assert "phantom" in caplog.text
        assert "ghost.md" in caplog.text

    def test_undeclared_write_warns(
        self, brain: BrainPaths, caplog: pytest.LogCaptureFixture
    ) -> None:
        """LLM writes a page it did not declare → warning."""

        def sneaky(cfg, backend, *, source_path, source_text):
            backend.write("wiki/concepts/rag.md", "---\ntitle: RAG\n---\n# RAG\n")
            return IngestionResult(summary="ok", new_pages=[])

        src = _make_source(brain)
        conn = get_connection(brain.db_path)
        try:
            with caplog.at_level(logging.WARNING, logger="llmwiki.services.ingest"):
                ingest_service.ingest(src, brain, conn, _cfg(brain), runner=sneaky)
        finally:
            conn.close()
        assert "did not declare" in caplog.text


class TestCancellation:
    def test_ingest_marks_job_cancelled(self, brain: BrainPaths) -> None:
        from llmwiki.core.errors import JobCancelledError
        from llmwiki.db.repo import JobRepo

        def cancelling_runner(cfg, backend, *, source_path, source_text):
            raise JobCancelledError("user cancelled")

        src = _make_source(brain)
        conn = get_connection(brain.db_path)
        try:
            jid = JobRepo(conn).create("ingest", status="running")
            with pytest.raises(JobCancelledError):
                ingest_service.ingest(
                    src, brain, conn, _cfg(brain), runner=cancelling_runner, job_id=jid
                )
            assert JobRepo(conn).get(jid)["status"] == "cancelled"
        finally:
            conn.close()


class TestCategoryConfidence:
    def test_create_category_and_confidence(self, brain: BrainPaths) -> None:
        src = _make_source(brain)
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(src, brain, conn, _cfg(brain), runner=_runner_writes_rag)
        finally:
            conn.close()
        change = cr.changes[0]
        assert change.category == "new"
        assert change.confidence == "high"

    def test_update_category(self, brain: BrainPaths) -> None:
        # Seed an existing page so the next write is an update.
        page = brain.wiki / "concepts" / "rag.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\ntitle: RAG\nconfidence: low\n---\n# RAG\nold\n", encoding="utf-8")

        def updater(cfg, backend, *, source_path, source_text):
            backend.write(
                "wiki/concepts/rag.md",
                "---\ntitle: RAG\nconfidence: medium\n---\n# RAG\nnew body\n",
            )
            return IngestionResult(summary="upd", affected_pages=["wiki/concepts/rag.md"])

        src = _make_source(brain, text="different content for update")
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(src, brain, conn, _cfg(brain), runner=updater)
        finally:
            conn.close()
        change = cr.changes[0]
        assert change.operation == "update"
        assert change.category == "edited"
        assert change.confidence == "medium"
