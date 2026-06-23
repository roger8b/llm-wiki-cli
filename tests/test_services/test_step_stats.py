"""Per-step ingestion timing aggregation for the dashboard (#280)."""

from __future__ import annotations

import json

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.services import stats_service


def _ingest_job(conn, durations: dict[str, int]) -> int:
    repo = JobRepo(conn)
    jid = repo.create("ingest", json.dumps({"source": "raw/x.txt"}), status="running")
    repo.complete(jid, result=json.dumps({"durations_ms": durations, "files": 1}))
    return jid


class TestStepStats:
    def test_empty_when_no_runs(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            stats = stats_service.step_stats(conn)
        finally:
            conn.close()
        assert stats["runs"] == 0
        assert stats["steps"] == []
        assert stats["regression"]["is_regression"] is False

    def test_averages_and_chunk_folding(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            # Oldest first; newest run is created last.
            _ingest_job(conn, {"extracting": 100, "chunk 1/2": 200, "chunk 2/2": 200})
            _ingest_job(conn, {"extracting": 200, "chunk 1/2": 400, "chunk 2/2": 400})
            stats = stats_service.step_stats(conn)
        finally:
            conn.close()

        assert stats["runs"] == 2
        steps = {s["name"]: s for s in stats["steps"]}
        # chunk passes fold into one bucket: run A=400, run B=800 -> avg 600.
        assert steps["chunk"]["avg_ms"] == 600.0
        assert steps["extracting"]["avg_ms"] == 150.0
        # "last_ms" is the newest run (the one created last).
        assert steps["chunk"]["last_ms"] == 800
        assert steps["extracting"]["last_ms"] == 200
        # Steps are ordered by average duration, descending.
        assert [s["name"] for s in stats["steps"]] == ["chunk", "extracting"]

    def test_regression_flagged_when_latest_spikes(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            _ingest_job(conn, {"running_agent": 100})
            _ingest_job(conn, {"running_agent": 100})
            _ingest_job(conn, {"running_agent": 500})  # newest: 5x the baseline
            stats = stats_service.step_stats(conn)
        finally:
            conn.close()
        reg = stats["regression"]
        assert reg["is_regression"] is True
        assert reg["latest_total_ms"] == 500
        assert reg["baseline_avg_ms"] == 100.0

    def test_no_regression_when_stable(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            _ingest_job(conn, {"running_agent": 100})
            _ingest_job(conn, {"running_agent": 105})
            stats = stats_service.step_stats(conn)
        finally:
            conn.close()
        assert stats["regression"]["is_regression"] is False

    def test_runs_without_durations_skipped(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            jid = repo.create("ingest", json.dumps({"source": "x"}), status="running")
            repo.complete(jid, result=json.dumps({"files": 0}))  # no durations_ms
            stats = stats_service.step_stats(conn)
        finally:
            conn.close()
        assert stats["runs"] == 0
