from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import change_request_service, ingest_service


def _fake_runner(
    cfg, backend: ChangeRequestBackend, *, source_path, source_text, source_meta=None
):
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


class TestApplyRevalidatesPaths:
    def test_apply_refuses_path_outside_allowlist(self, brain: BrainPaths) -> None:
        """Defence in depth: even if a tampered CR slips a bad path into
        meta.json, apply() must refuse before writing anything to disk."""
        import json

        from llmwiki.core.models import FileChange

        change = FileChange(
            path="wiki/concepts/rag.md",
            operation="create",
            new_content="# RAG\n",
            diff="",
        )
        conn = get_connection(brain.db_path)
        try:
            cr = change_request_service.create_from_changes(
                [change], "ok", brain, conn
            )
            # Tamper with the persisted meta.json: inject a path outside wiki/.
            meta_path = Path(cr.diff_dir) / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["changes"][0]["path"] = ".llmwiki/config.toml"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            with pytest.raises(ValueError, match="refusing to apply"):
                change_request_service.apply(cr.id, brain, conn)
        finally:
            conn.close()
        # nothing escaped the sandbox
        assert not (brain.root / ".llmwiki/config.toml").exists()


class TestRawGuard:
    def test_agent_cannot_write_raw(self, brain: BrainPaths) -> None:
        def evil_runner(cfg, backend, *, source_path, source_text, source_meta=None):
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


class TestQualityPersistence:
    def test_quality_round_trips_through_meta(self, brain: BrainPaths) -> None:
        cr = _ingest(brain)
        conn = get_connection(brain.db_path)
        try:
            reloaded = change_request_service.get(cr.id, conn)
        finally:
            conn.close()
        assert reloaded is not None
        change = reloaded.changes[0]
        assert change.quality_score is not None
        assert isinstance(change.quality_flags, list)

    def test_old_change_without_quality_loads(self) -> None:
        from llmwiki.core.models import FileChange

        # A CR persisted before #168 has no quality fields.
        legacy = {"path": "wiki/x.md", "operation": "create", "diff": "+x"}
        change = FileChange.model_validate(legacy)
        assert change.quality_score is None
        assert change.quality_flags == []
