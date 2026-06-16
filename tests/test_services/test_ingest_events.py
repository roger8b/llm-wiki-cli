"""Live-progress events emitted during ingestion (#272)."""

from __future__ import annotations

from pathlib import Path

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobEventRepo, JobRepo
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import ingest_service

GOOD = "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n# RAG\nBody.\n"


def _src(brain: BrainPaths) -> Path:
    src = brain.raw / "articles" / "art.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("about rag", encoding="utf-8")
    return src


def _events(brain: BrainPaths, job_id: int) -> list[tuple[str, dict]]:
    import json

    conn = get_connection(brain.db_path)
    try:
        rows = JobEventRepo(conn).since(job_id, 0)
        return [(r["kind"], json.loads(r["payload"]) if r["payload"] else {}) for r in rows]
    finally:
        conn.close()


class TestIngestEvents:
    def test_step_and_page_events_emitted(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            backend.write("wiki/concepts/rag.md", GOOD)
            return IngestionResult(summary="ok", new_pages=["wiki/concepts/rag.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                _src(brain), brain, conn, WorkspaceConfig(brain_root=brain.root), runner=runner
            )
            job_id = JobRepo(conn).list()[0]["id"]
        finally:
            conn.close()

        events = _events(brain, job_id)
        kinds = [k for k, _ in events]
        # Coarse steps are mirrored into the timeline...
        steps = [p["name"] for k, p in events if k == "step"]
        assert "extracting" in steps
        assert "running_agent" in steps
        assert "creating_change_request" in steps
        # ...and the page write the agent staged shows up as a page_write event.
        assert "page_write" in kinds
        page_events = [p for k, p in events if k == "page_write"]
        assert page_events[0]["path"] == "wiki/concepts/rag.md"
        assert page_events[0]["op"] == "create"
        # No event payload leaks the page body.
        for _, payload in events:
            assert GOOD not in str(payload)
        assert cr is not None

    def test_empty_result_emits_warning(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            # Agent writes nothing → empty CR; the reason must reach the timeline.
            return IngestionResult(summary="", new_pages=[])

        conn = get_connection(brain.db_path)
        try:
            ingest_service.ingest(
                _src(brain), brain, conn, WorkspaceConfig(brain_root=brain.root), runner=runner
            )
            job_id = JobRepo(conn).list()[0]["id"]
        finally:
            conn.close()

        warnings = [p for k, p in _events(brain, job_id) if k == "warning"]
        assert warnings, "empty ingestion should emit a warning event"


class TestIngestionEventHandler:
    def test_tool_calls_become_events(self) -> None:
        from llmwiki.llm_agents.streaming import make_ingestion_event_handler

        seen: list[tuple[str, dict]] = []
        handler = make_ingestion_event_handler(lambda kind, payload: seen.append((kind, payload)))

        handler.on_tool_start({"name": "search_pages"}, "query=rag")
        handler.on_tool_end("result", name="search_pages")
        assert seen[0][0] == "tool_start"
        assert seen[0][1]["tool"] == "search_pages"
        assert seen[1][0] == "tool_end"

    def test_arg_preview_drops_content(self) -> None:
        from llmwiki.llm_agents.streaming import make_ingestion_event_handler

        seen: list[tuple[str, dict]] = []
        handler = make_ingestion_event_handler(lambda kind, payload: seen.append((kind, payload)))
        handler.on_tool_start(
            {"name": "write_file"},
            {"file_path": "wiki/concepts/rag.md", "content": "SECRET BODY"},
        )
        assert "SECRET BODY" not in seen[0][1]["args"]
        assert "wiki/concepts/rag.md" in seen[0][1]["args"]
