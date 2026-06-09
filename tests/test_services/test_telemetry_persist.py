"""Telemetry persistence + lint CR cross-reference (epic #119)."""

from __future__ import annotations

import json
from pathlib import Path

from llmwiki.agents.backend import ChangeRequestBackend
from llmwiki.agents.models import IngestionResult
from llmwiki.agents.telemetry import ExecutionMeta
from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import FileChange, LintFinding
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import change_request_service, ingest_service, lint_service


def _runner_with_meta(cfg, backend: ChangeRequestBackend, *, source_path, source_text):
    backend.write("wiki/concepts/rag.md", "---\ntitle: RAG\n---\n# RAG\nbody\n")
    backend.execution_meta = ExecutionMeta(
        model="ollama:test", tokens_in=120, tokens_out=45, tool_calls=2, latency_ms=999
    )
    return IngestionResult(summary="created", new_pages=["wiki/concepts/rag.md"])


class TestExecutionPersisted:
    def test_meta_json_has_execution_block(self, brain: BrainPaths) -> None:
        src = brain.raw / "articles" / "a.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("about rag", encoding="utf-8")
        cfg = WorkspaceConfig(brain_root=brain.root)
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(src, brain, conn, cfg, runner=_runner_with_meta)
        finally:
            conn.close()
        meta = json.loads((Path(cr.diff_dir) / "meta.json").read_text(encoding="utf-8"))
        assert meta["execution"]["model"] == "ollama:test"
        assert meta["execution"]["tokens_in"] == 120
        assert meta["execution"]["tool_calls"] == 2


class TestLintCrossReference:
    def test_annotate_attaches_related_cr(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            change = FileChange(
                path="wiki/concepts/rag.md",
                operation="create",
                new_content="# RAG\n",
                diff="",
            )
            cr = change_request_service.create_from_changes([change], "fix", brain, conn)

            findings = [
                LintFinding(kind="broken_link", message="x", pages=["wiki/concepts/rag.md"]),
                LintFinding(kind="orphan_page", message="y", pages=["wiki/concepts/other.md"]),
            ]
            annotated = lint_service.annotate_with_pending_crs(findings, conn)
        finally:
            conn.close()
        assert annotated[0].related_cr == cr.id
        assert annotated[1].related_cr is None
