"""API: per-step ingestion timing aggregate endpoint (#280)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _ingest(brain: BrainPaths, durations: dict[str, int]) -> None:
    conn = get_connection(brain.db_path)
    try:
        repo = JobRepo(conn)
        jid = repo.create("ingest", status="running")
        repo.complete(jid, result=json.dumps({"durations_ms": durations, "files": 1}))
    finally:
        conn.close()


class TestStepStatsEndpoint:
    def test_returns_aggregated_steps(self, client, brain: BrainPaths) -> None:
        _ingest(brain, {"extracting": 100, "chunk 1/2": 200, "chunk 2/2": 200})
        _ingest(brain, {"extracting": 200, "chunk 1/2": 400, "chunk 2/2": 400})

        resp = client.get("/api/jobs/stats/steps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["runs"] == 2
        names = {s["name"] for s in body["steps"]}
        assert names == {"chunk", "extracting"}
        assert "regression" in body

    def test_empty_brain_ok(self, client) -> None:
        resp = client.get("/api/jobs/stats/steps")
        assert resp.status_code == 200
        assert resp.json()["runs"] == 0

    def test_not_shadowed_by_job_id_route(self, client, brain: BrainPaths) -> None:
        # "/jobs/stats/steps" must not be captured by "/jobs/{job_id}".
        _ingest(brain, {"running_agent": 100})
        resp = client.get("/api/jobs/stats/steps")
        assert resp.status_code == 200
        assert "steps" in resp.json()
