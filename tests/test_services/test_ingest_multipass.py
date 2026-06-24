"""Multi-pass ingestion for long sources (#162).

Drives ``ingest_service.ingest`` with fake runners (no LLM): a programmable
outline runner and a chunk runner that stages one page per outline concept,
reusing the shared backend so intra-source dedup is exercised.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.errors import JobCancelledError
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult, OutlinePlan
from llmwiki.llm_agents.telemetry import ExecutionMeta
from llmwiki.services import ingest_service

CONCEPTS = [f"Concept {i}" for i in range(8)]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def _long_source(brain: BrainPaths) -> Path:
    # ~100k chars, each concept mentioned in its own block spread across the text.
    blocks: list[str] = []
    filler = "lorem ipsum dolor sit amet " * 40
    for rep in range(5):
        for c in CONCEPTS:
            blocks.append(f"## {c} (mention {rep})\n\n{filler}\n")
    text = "\n\n".join(blocks)
    assert len(text) > 24000
    src = brain.raw / "articles" / "long.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(text, encoding="utf-8")
    return src


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


def _outline_runner(cfg, *, source_meta=None, chunk_summaries):
    return OutlinePlan(concepts=list(CONCEPTS), summary="A long source.")


class _ChunkRunner:
    """Stages a page per outline concept; dedup overlay prevents duplicates."""

    def __init__(self) -> None:
        self.calls = 0
        self.parts: list = []

    def __call__(
        self, cfg, backend: ChangeRequestBackend, *, source_path, source_text,
        source_meta=None, outline=None, part=None,
    ) -> IngestionResult:
        self.calls += 1
        self.parts.append(part)
        written: list[str] = []
        for concept in (outline.concepts if outline else []):
            path = f"wiki/concepts/{_slug(concept)}.md"
            backend.write(
                path,
                f"---\ntitle: {concept}\ntype: concept\nconfidence: high\n---\n"
                f"# {concept}\n\nBody for {concept}.\n",
            )
            written.append(path)
        backend.execution_meta = ExecutionMeta(
            model=cfg.model, tokens_in=100, tokens_out=50, tool_calls=1, latency_ms=10
        )
        return IngestionResult(summary=f"part {part}", new_pages=written)


class TestMultiPass:
    def test_single_cr_with_unique_pages(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        runner = _ChunkRunner()
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                src, brain, conn, _cfg(brain),
                runner=runner, outline_runner=_outline_runner,
            )
        finally:
            conn.close()
        assert runner.calls > 1  # multiple chunk passes
        paths = [c.path for c in cr.changes]
        assert len(paths) == len(set(paths))  # unique slugs, no duplicates
        assert cr.files_changed >= 8

    def test_progress_reports_outline_and_chunks(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        seen: list[str] = []
        orig = JobRepo.set_progress

        def spy(self, job_id, step):
            seen.append(step)
            return orig(self, job_id, step)

        conn = get_connection(brain.db_path)
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(JobRepo, "set_progress", spy)
                ingest_service.ingest(
                    src, brain, conn, _cfg(brain),
                    runner=_ChunkRunner(), outline_runner=_outline_runner,
                )
        finally:
            conn.close()
        assert "outlining" in seen
        assert any(s.startswith("chunk 1/") for s in seen)

    def test_execution_meta_aggregated(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        runner = _ChunkRunner()
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                src, brain, conn, _cfg(brain),
                runner=runner, outline_runner=_outline_runner,
            )
            import json

            meta = json.loads(
                (Path(cr.diff_dir) / "meta.json").read_text(encoding="utf-8")
            )
        finally:
            conn.close()
        execution = meta["execution"]
        assert execution is not None
        # tokens summed across all chunk passes (100 in / 50 out each).
        assert execution["tokens_in"] == 100 * runner.calls
        assert execution["tokens_out"] == 50 * runner.calls

    def test_cancellation_between_passes_creates_no_cr(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        conn = get_connection(brain.db_path)

        def cancel_check() -> bool:
            return True  # cancelled before the first chunk pass

        try:
            jid = JobRepo(conn).create("ingest", status="running")
            with pytest.raises(JobCancelledError):
                ingest_service.ingest(
                    src, brain, conn, _cfg(brain),
                    runner=_ChunkRunner(), outline_runner=_outline_runner,
                    job_id=jid, cancel_check=cancel_check,
                )
            assert JobRepo(conn).get(jid)["status"] == "cancelled"
            from llmwiki.services import change_request_service

            assert change_request_service.list_crs(conn) == []
        finally:
            conn.close()

    def test_scoped_concepts_change_each_chunk_but_keep_global_fallback(
        self, brain: BrainPaths
    ) -> None:
        src = brain.raw / "articles" / "scoped.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("Alpha only.\n\nBeta only.\n\n", encoding="utf-8")
        seen: list[list[str]] = []

        def outline_runner(cfg, *, source_meta=None, chunk_summaries=None):
            return OutlinePlan(concepts=["Alpha", "Beta", "Global"], summary="s")

        def runner(
            cfg, backend, *, source_path, source_text, source_meta=None, outline=None, part=None
        ):
            concepts = list(outline.concepts)
            seen.append(concepts)
            for concept in concepts:
                backend.write(
                    f"wiki/concepts/{_slug(concept)}.md",
                    f"---\ntitle: {concept}\ntype: concept\nconfidence: high\n---\n"
                    f"# {concept}\n\nBody.\n",
                )
            return IngestionResult(summary="ok", new_pages=[])

        cfg = WorkspaceConfig(
            brain_root=brain.root,
            chunk_threshold_chars=1,
            chunk_size_chars=20,
            chunk_overlap_chars=0,
            ingest_chunk_concurrency=1,
        )
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                src, brain, conn, cfg, runner=runner, outline_runner=outline_runner
            )
        finally:
            conn.close()
        assert seen == [["Alpha", "Global"], ["Beta", "Global"]]
        assert {c.path for c in cr.changes} == {
            "wiki/concepts/alpha.md",
            "wiki/concepts/beta.md",
            "wiki/concepts/global.md",
        }

    def test_scoped_concepts_flag_false_keeps_global_outline(self, brain: BrainPaths) -> None:
        src = brain.raw / "articles" / "global.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("Alpha only.\n\nBeta only.\n\n", encoding="utf-8")
        seen: list[list[str]] = []

        def outline_runner(cfg, *, source_meta=None, chunk_summaries=None):
            return OutlinePlan(concepts=["Alpha", "Beta"], summary="s")

        def runner(
            cfg, backend, *, source_path, source_text, source_meta=None, outline=None, part=None
        ):
            seen.append(list(outline.concepts))
            concept = f"Seen {part[0]}"
            backend.write(
                f"wiki/concepts/seen-{part[0]}.md",
                f"---\ntitle: {concept}\ntype: concept\nconfidence: high\n---\n# {concept}\n",
            )
            return IngestionResult(summary="ok", new_pages=[])

        cfg = WorkspaceConfig(
            brain_root=brain.root,
            chunk_threshold_chars=1,
            chunk_size_chars=20,
            chunk_overlap_chars=0,
            ingest_chunk_concurrency=1,
            ingest_scope_concepts_per_chunk=False,
        )
        conn = get_connection(brain.db_path)
        try:
            ingest_service.ingest(
                src, brain, conn, cfg, runner=runner, outline_runner=outline_runner
            )
        finally:
            conn.close()
        assert seen == [["Alpha", "Beta"], ["Alpha", "Beta"]]


class TestShortSourceRegression:
    def test_short_source_single_invocation(self, brain: BrainPaths) -> None:
        src = brain.raw / "articles" / "short.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("short content about rag", encoding="utf-8")
        calls = {"runner": 0, "outline": 0}

        def runner(cfg, backend, *, source_path, source_text, source_meta=None):
            calls["runner"] += 1
            backend.write(
                "wiki/concepts/rag.md",
                "---\ntitle: RAG\ntype: concept\n---\n# RAG\nbody\n",
            )
            return IngestionResult(summary="ok", new_pages=["wiki/concepts/rag.md"])

        def outline_runner(cfg, *, source_meta=None, chunk_summaries):
            calls["outline"] += 1
            return OutlinePlan()

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                src, brain, conn, _cfg(brain),
                runner=runner, outline_runner=outline_runner,
            )
        finally:
            conn.close()
        assert calls["runner"] == 1  # no extra cost
        assert calls["outline"] == 0  # outline never runs for short sources
        assert cr.files_changed == 1
