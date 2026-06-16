"""Per-step durations and live per-pass telemetry during ingestion (#273)."""

from __future__ import annotations

import json
from pathlib import Path

from test_ingest_multipass import _ChunkRunner, _long_source, _outline_runner

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobEventRepo, JobRepo
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.llm_agents.telemetry import ExecutionMeta
from llmwiki.services import ingest_service

GOOD = "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n# RAG\nBody.\n"


def _src(brain: BrainPaths) -> Path:
    src = brain.raw / "articles" / "art.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("about rag", encoding="utf-8")
    return src


def _events(brain: BrainPaths, job_id: int) -> list[tuple[str, dict]]:
    conn = get_connection(brain.db_path)
    try:
        return [
            (r["kind"], json.loads(r["payload"]) if r["payload"] else {})
            for r in JobEventRepo(conn).since(job_id, 0)
        ]
    finally:
        conn.close()


def _last_job(brain: BrainPaths) -> dict:
    conn = get_connection(brain.db_path)
    try:
        return dict(JobRepo(conn).list()[0])
    finally:
        conn.close()


class TestSinglePassTelemetry:
    def test_durations_and_one_telemetry(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            backend.write("wiki/concepts/rag.md", GOOD)
            backend.execution_meta = ExecutionMeta(
                model=cfg.model, tokens_in=100, tokens_out=50, tool_calls=2, latency_ms=12
            )
            return IngestionResult(summary="ok", new_pages=["wiki/concepts/rag.md"])

        conn = get_connection(brain.db_path)
        try:
            ingest_service.ingest(
                _src(brain), brain, conn, WorkspaceConfig(brain_root=brain.root), runner=runner
            )
        finally:
            conn.close()

        job = _last_job(brain)
        durations = json.loads(job["result"])["durations_ms"]
        # Every coarse step has a measured duration.
        assert {"extracting", "running_agent", "creating_change_request"} <= set(durations)
        assert all(v >= 0 for v in durations.values())

        events = _events(brain, job["id"])
        telem = [p for k, p in events if k == "telemetry"]
        assert len(telem) == 1  # single pass still emits one telemetry event
        assert telem[0]["tokens_in"] == 100
        # Steps emit a start and an end (with duration_ms) for each phase.
        ends = [p for k, p in events if k == "step" and p.get("status") == "end"]
        assert all("duration_ms" in p for p in ends)


class TestMultiPassTelemetry:
    def test_per_pass_events_sum_to_merge(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        conn = get_connection(brain.db_path)
        try:
            ingest_service.ingest(
                src, brain, conn, WorkspaceConfig(brain_root=brain.root),
                runner=_ChunkRunner(), outline_runner=_outline_runner,
            )
        finally:
            conn.close()

        job = _last_job(brain)
        events = _events(brain, job["id"])
        chunk_telem = [p for k, p in events if k == "telemetry" and p.get("phase") == "chunk"]
        assert len(chunk_telem) > 1  # one per chunk pass, emitted as it finishes

        # Sum of per-pass telemetry == the merged execution total on the job.
        merged = json.loads(job["result"])["execution"]
        assert sum(p["tokens_in"] for p in chunk_telem) == merged["tokens_in"]
        assert sum(p["tool_calls"] for p in chunk_telem) == merged["tool_calls"]

    def test_pages_staged_is_monotonic(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        conn = get_connection(brain.db_path)
        try:
            ingest_service.ingest(
                src, brain, conn, WorkspaceConfig(brain_root=brain.root),
                runner=_ChunkRunner(), outline_runner=_outline_runner,
            )
        finally:
            conn.close()

        job = _last_job(brain)
        counts = [
            p["pages_staged"]
            for _, p in _events(brain, job["id"])
            if "pages_staged" in p
        ]
        assert counts == sorted(counts)  # never decreases
        assert counts[-1] >= 8
