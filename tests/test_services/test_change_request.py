from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.agents.backend import ChangeRequestBackend
from llmwiki.agents.models import IngestionResult
from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import change_request_service, ingest_service


def _fake_runner(cfg, backend: ChangeRequestBackend, *, source_path, source_text):
    """Runner determinístico que simula o agente escrevendo páginas."""
    backend.write(
        "wiki/concepts/rag.md",
        f"---\ntitle: RAG\ntype: concept\nsources: [{source_path}]\n---\n# RAG\nResumo.\n",
    )
    return IngestionResult(summary="Criou página RAG.", new_pages=["wiki/concepts/rag.md"])


def _ingest(brain: BrainPaths, text: str = "conteúdo sobre rag"):
    src = brain.raw / "articles" / "art.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(text, encoding="utf-8")
    cfg = WorkspaceConfig(brain_root=brain.root)
    conn = get_connection(brain.db_path)
    try:
        return ingest_service.ingest(src, brain, conn, cfg, runner=_fake_runner)
    finally:
        conn.close()


class TestIngestCreatesCR:
    def test_creates_pending_cr_without_writing_wiki(self, brain: BrainPaths) -> None:
        cr = _ingest(brain)
        assert cr.files_changed == 1
        assert cr.changes[0].operation == "create"
        # nada escrito na wiki ainda
        assert not (brain.root / "wiki/concepts/rag.md").exists()
        # meta.json persistido
        assert (Path(cr.diff_dir) / "meta.json").exists()

    def test_cr_id_sequential(self, brain: BrainPaths) -> None:
        cr1 = _ingest(brain)
        cr2 = _ingest(brain, text="outro conteúdo diferente")
        assert cr1.id.endswith("0001")
        assert cr2.id.endswith("0002")


class TestApplyReject:
    def test_apply_writes_wiki_and_reindexes(self, brain: BrainPaths) -> None:
        cr = _ingest(brain)
        conn = get_connection(brain.db_path)
        try:
            applied = change_request_service.apply(cr.id, brain, conn)
        finally:
            conn.close()
        assert applied.status == "applied"
        page = brain.root / "wiki/concepts/rag.md"
        assert page.exists()
        assert "# RAG" in page.read_text(encoding="utf-8")
        # index.md regenerado
        assert "RAG" in brain.index_path.read_text(encoding="utf-8")
        # log atualizado
        assert cr.id in brain.log_path.read_text(encoding="utf-8")

    def test_apply_twice_fails(self, brain: BrainPaths) -> None:
        cr = _ingest(brain)
        conn = get_connection(brain.db_path)
        try:
            change_request_service.apply(cr.id, brain, conn)
            with pytest.raises(ValueError):
                change_request_service.apply(cr.id, brain, conn)
        finally:
            conn.close()

    def test_reject_does_not_write(self, brain: BrainPaths) -> None:
        cr = _ingest(brain)
        conn = get_connection(brain.db_path)
        try:
            change_request_service.reject(cr.id, conn)
            row = change_request_service.get(cr.id, conn)
        finally:
            conn.close()
        assert row.status == "rejected"
        assert not (brain.root / "wiki/concepts/rag.md").exists()


class TestRawGuard:
    def test_agent_cannot_write_raw(self, brain: BrainPaths) -> None:
        def evil_runner(cfg, backend, *, source_path, source_text):
            res = backend.write("raw/articles/hack.md", "x")
            assert res.error is not None
            return IngestionResult(summary="tentou raw")

        src = brain.raw / "articles" / "a.md"
        src.write_text("x", encoding="utf-8")
        cfg = WorkspaceConfig(brain_root=brain.root)
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(src, brain, conn, cfg, runner=evil_runner)
        finally:
            conn.close()
        assert cr.files_changed == 0
