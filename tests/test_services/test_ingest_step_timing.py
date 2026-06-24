"""Per-step timing instrumentation + baseline harness (#276).

The mandatory first story of epic #271: every ingestion step is timed and the
``durations_ms`` map is persisted in BOTH the job result and the CR's
``meta.json`` so later optimizations (#277-#279) can be measured against a real
baseline. Also smoke-tests the ``scripts/ingest_baseline.py`` harness end-to-end
with a fake runner (no LLM).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.llm_agents.models import IngestionResult, OutlinePlan
from llmwiki.llm_agents.telemetry import ExecutionMeta
from llmwiki.services import ingest_service
from llmwiki.services.ingest_service import _StepTracker


class _StubJobRepo:
    """Minimal JobRepo surface used by _StepTracker (records progress labels)."""

    def __init__(self) -> None:
        self.progress: list[str] = []

    def set_progress(self, job_id: int, step: str) -> None:
        self.progress.append(step)


class TestStepTracker:
    def test_repeated_step_names_accumulate(self) -> None:
        tracker = _StepTracker(emit=None, job_repo=_StubJobRepo(), job_id=1)
        tracker.step("chunk")
        tracker.step("chunk")  # closes first, opens second under the same name
        tracker.finish()
        # Same-named steps sum into a single key (e.g. "chunk 1/3" + "chunk 2/3").
        assert list(tracker.durations) == ["chunk"]
        assert tracker.durations["chunk"] >= 0

    def test_distinct_steps_recorded_separately(self) -> None:
        repo = _StubJobRepo()
        tracker = _StepTracker(emit=None, job_repo=repo, job_id=1)
        tracker.step("outlining")
        tracker.step("creating_change_request")
        tracker.finish()
        assert set(tracker.durations) == {"outlining", "creating_change_request"}
        assert repo.progress == ["outlining", "creating_change_request"]

    def test_finish_is_idempotent(self) -> None:
        tracker = _StepTracker(emit=None, job_repo=_StubJobRepo(), job_id=1)
        tracker.step("extract")
        tracker.finish()
        tracker.finish()  # no open step -> no-op, no double count
        assert list(tracker.durations) == ["extract"]


CONCEPTS = [f"Concept {i}" for i in range(8)]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def _long_text() -> str:
    # Long enough (>24k chars) to trigger the multi-pass (outline + chunk) path.
    blocks = [
        "lorem ipsum dolor sit amet " * 40 + f"\n## {c}\n"
        for c in CONCEPTS
        for _ in range(5)
    ]
    text = "\n\n".join(blocks)
    assert len(text) > 24000
    return text


def _long_source(brain: BrainPaths) -> Path:
    src = brain.raw / "articles" / "long.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(_long_text(), encoding="utf-8")
    return src


def _outline_runner(cfg, *, source_meta=None, chunk_summaries):
    return OutlinePlan(concepts=list(CONCEPTS), summary="A long source.")


def _chunk_runner(
    cfg, backend, *, source_path, source_text, source_meta=None, outline=None, part=None
):
    for concept in outline.concepts if outline else []:
        backend.write(
            f"wiki/concepts/{_slug(concept)}.md",
            f"---\ntitle: {concept}\ntype: concept\nconfidence: high\n---\n# {concept}\n\nBody.\n",
        )
    backend.execution_meta = ExecutionMeta(
        model=cfg.model, tokens_in=100, tokens_out=50, tool_calls=1, latency_ms=10
    )
    return IngestionResult(summary=f"part {part}", new_pages=[])


class TestDurationsPersisted:
    def test_durations_in_job_result_and_cr_meta(self, brain: BrainPaths) -> None:
        src = _long_source(brain)
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                src, brain, conn, WorkspaceConfig(brain_root=brain.root),
                runner=_chunk_runner, outline_runner=_outline_runner,
            )
            job = dict(JobRepo(conn).list()[0])
        finally:
            conn.close()

        result_durations = json.loads(job["result"])["durations_ms"]
        meta = json.loads((Path(cr.diff_dir) / "meta.json").read_text(encoding="utf-8"))
        meta_durations = meta["durations_ms"]

        # The map is non-empty, covers the real pipeline steps, and the CR's
        # meta.json carries the same baseline the job result does.
        assert meta_durations == result_durations
        assert "outlining" in result_durations
        assert "creating_change_request" in result_durations
        assert any(k.startswith("chunk ") for k in result_durations)
        assert all(isinstance(v, int) and v >= 0 for v in result_durations.values())


class TestBaselineHarness:
    """Smoke the scripts/ingest_baseline.py harness without hitting an LLM."""

    @staticmethod
    def _load_harness():
        path = Path(__file__).resolve().parents[2] / "scripts" / "ingest_baseline.py"
        spec = importlib.util.spec_from_file_location("ingest_baseline", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_run_one_with_fake_runner_reports_durations(self) -> None:
        harness = self._load_harness()
        # Long source so the injected fake runners exercise outline + chunks.
        run = harness.run_one(
            "smoke", _long_text(), runner=_chunk_runner, outline_runner=_outline_runner,
        )
        assert run["durations_ms"]
        assert run["files_changed"] >= 1

    def test_render_produces_markdown_report(self) -> None:
        harness = self._load_harness()
        runs = [{
            "name": "smoke", "chars": 1234, "model": "anthropic:test",
            "durations_ms": {"outlining": 10, "chunk 1/2": 20, "collect": 5},
            "execution": {"tokens_in": 100, "tokens_out": 50},
            "files_changed": 3, "event_counts": {"step": 6},
        }]
        report = harness.render(runs)
        assert "Ingestion baseline" in report
        assert "smoke" in report

    def test_seed_pages_populates_brain_and_records_size(self) -> None:
        # #295: seeding the throwaway brain makes wiki_stats/search/dedup see a
        # real corpus. Index FTS-only (no global embedding model) for speed.
        harness = self._load_harness()
        harness.load_config = lambda paths: WorkspaceConfig(brain_root=paths.root)
        run = harness.run_one(
            "smoke", _long_text(),
            runner=_chunk_runner, outline_runner=_outline_runner, seed_pages=12,
        )
        assert run["label"] == "populated"
        assert run["pages_in_brain"] == 12  # the synthetic corpus was indexed
        assert run["files_changed"] >= 1

    def test_render_shows_empty_vs_populated_delta(self) -> None:
        harness = self._load_harness()
        runs = [
            {
                "name": "long", "label": "empty", "pages_in_brain": 0, "chars": 1000,
                "model": "m", "durations_ms": {"outlining": 10000, "chunk 1/1": 20000},
                "execution": {}, "files_changed": 2, "event_counts": {},
                "tool_calls_by_name": {}, "explore_calls": 1,
            },
            {
                "name": "long", "label": "populated", "pages_in_brain": 200, "chars": 1000,
                "model": "m", "durations_ms": {"outlining": 15000, "chunk 1/1": 40000},
                "execution": {}, "files_changed": 2, "event_counts": {},
                "tool_calls_by_name": {"search_pages": 9}, "explore_calls": 9,
            },
        ]
        report = harness.render(runs)
        assert "Empty vs populated" in report
        assert "200-page brain" in report
        assert "+20.0s" in report  # chunk delta surfaced
