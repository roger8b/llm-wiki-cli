"""SSE replay of the ingestion event timeline (#274)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobEventRepo, JobRepo


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _done_job_with_events(brain: BrainPaths) -> tuple[int, list[int]]:
    conn = get_connection(brain.db_path)
    try:
        jid = JobRepo(conn).create("ingest", status="running")
        ev = JobEventRepo(conn)
        ids = [
            ev.append(jid, "step", {"name": "extracting"}),
            ev.append(jid, "page_write", {"path": "wiki/concepts/rag.md", "op": "create"}),
            ev.append(jid, "telemetry", {"tokens_in": 100, "pages_staged": 1}),
        ]
        JobRepo(conn).complete(jid, result='{"cr": "CR-1", "files": 1}')
        return jid, ids
    finally:
        conn.close()


class TestIngestEventSSE:
    def test_replays_events_then_result(self, client, brain: BrainPaths) -> None:
        jid, _ = _done_job_with_events(brain)
        body = client.get(f"/api/jobs/{jid}/events").text
        # Each appended event is replayed as an ingest_event frame...
        assert "event: ingest_event" in body
        assert '"kind": "page_write"' in body
        assert '"kind": "telemetry"' in body
        # ...and the terminal result still lands.
        assert "event: result" in body
        assert "event: end" in body

    def test_after_event_id_skips_seen(self, client, brain: BrainPaths) -> None:
        jid, ids = _done_job_with_events(brain)
        # Resume after the first two events: only the telemetry one should remain.
        body = client.get(
            f"/api/jobs/{jid}/events", params={"after_event_id": ids[1]}
        ).text
        assert '"kind": "telemetry"' in body
        assert '"kind": "page_write"' not in body
        assert '"name": "extracting"' not in body
