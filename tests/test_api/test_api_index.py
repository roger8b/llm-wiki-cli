"""Tests for /api/index/* endpoints (#305): reindex job + status drift/embeddings."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo, MetaRepo


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _seed_pages(brain: BrainPaths, names: list[str]) -> None:
    for n in names:
        p = brain.wiki / "concepts" / f"{n}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"---\ntitle: {n.title()}\ntype: concept\n---\n# {n.title()}\nbody\n",
            encoding="utf-8",
        )


def _wait_for_job(brain: BrainPaths, job_id: int, status: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    conn = get_connection(brain.db_path, apply_schema=False)
    try:
        while time.monotonic() < deadline:
            row = JobRepo(conn).get(job_id)
            if row is not None and row["status"] == status:
                return dict(row)
            time.sleep(0.05)
        row = JobRepo(conn).get(job_id)
        raise AssertionError(
            f"job {job_id} did not reach '{status}' in {timeout}s "
            f"(last status: {row['status'] if row else None})"
        )
    finally:
        conn.close()


class TestReindexEndpoint:
    """AC1: POST /index/reindex creates a queued 'index' job and returns job_id."""

    def test_post_reindex_creates_queued_job(self, client, brain: BrainPaths) -> None:
        r = client.post("/api/index/reindex")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "job_id" in body
        # Inspect the persisted job row: type="index", payload has embeddings=true default.
        conn = get_connection(brain.db_path)
        try:
            row = JobRepo(conn).get(body["job_id"])
        finally:
            conn.close()
        assert row is not None
        assert row["type"] == "index"
        assert row["status"] == "queued"
        payload = json.loads(row["payload"])
        assert payload.get("embeddings") is True

    def test_post_reindex_respects_embeddings_false(self, client, brain: BrainPaths) -> None:
        r = client.post("/api/index/reindex", json={"embeddings": False})
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        conn = get_connection(brain.db_path)
        try:
            row = JobRepo(conn).get(job_id)
        finally:
            conn.close()
        assert row is not None
        assert json.loads(row["payload"]).get("embeddings") is False


class TestStatusEndpoint:
    """AC2: GET /index/status reports db_pages, disk_files, drift, stale,
    embeddings.{count,expected,enabled}, last_reindex_at."""

    def test_empty_brain_reports_zeros(self, client) -> None:
        r = client.get("/api/index/status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["db_pages"] == 0
        assert body["disk_files"] == 0
        assert body["drift"] == 0
        assert body["stale"] is False
        assert body["embeddings"] == {"count": 0, "expected": 0, "enabled": False}
        assert body["last_reindex_at"] is None

    def test_status_after_reindex_is_in_sync(
        self, client, brain: BrainPaths, monkeypatch
    ) -> None:
        _seed_pages(brain, ["rag", "vectors", "agents"])
        # Run reindex synchronously (no worker) by hitting the runner path
        # directly. Status should reflect db_pages == disk_files == 3.
        from llmwiki.core.config import load_config
        from llmwiki.db.connection import get_connection
        from llmwiki.services import index_service

        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, load_config(brain))
            index_service.rebuild_index_md(brain, conn)
        finally:
            conn.close()

        r = client.get("/api/index/status")
        body = r.json()
        assert body["db_pages"] == 3
        assert body["disk_files"] == 3
        assert body["drift"] == 0
        assert body["stale"] is False

    def test_status_detects_drift_when_disk_exceeds_db(
        self, client, brain: BrainPaths
    ) -> None:
        """AC3: 3 files on disk, 0 in db → drift=3, stale=true."""
        _seed_pages(brain, ["one", "two", "three"])
        r = client.get("/api/index/status")
        body = r.json()
        assert body["disk_files"] == 3
        assert body["db_pages"] == 0
        assert body["drift"] == 3
        assert body["stale"] is True

    def test_status_reports_embeddings_enabled_when_configured(
        self, client, brain: BrainPaths
    ) -> None:
        """When cfg.embedding_model is set, status.embeddings.enabled=true."""
        client.patch("/api/config", json={"embedding_model": "ollama:nomic-embed"})
        r = client.get("/api/index/status")
        body = r.json()
        assert body["embeddings"]["enabled"] is True
        # expected ≈ db_pages (0 here); count is the actual rows in page_embeddings.
        assert body["embeddings"]["expected"] == body["db_pages"]
        assert body["embeddings"]["count"] == 0


class TestReindexJobRunsAndPersists:
    """AC4 + AC5: reindex runs as a job (not blocking), SSE emits events,
    last_reindex_at persists across reconnections."""

    def test_post_reindex_returns_job_id_immediately(self, client) -> None:
        # AC4: the HTTP request returns immediately with a job_id; the work
        # happens in the background.
        t0 = time.monotonic()
        r = client.post("/api/index/reindex")
        elapsed = time.monotonic() - t0
        assert r.status_code == 200
        assert elapsed < 1.0, f"POST took {elapsed:.2f}s — should be non-blocking"

    def test_worker_processes_index_job_and_persists_last_reindex_at(
        self, client, brain: BrainPaths
    ) -> None:
        """End-to-end: POST → worker picks up → wiki_pages populated → status in sync.
        AC5: last_reindex_at is persisted and survives a DB close/reopen."""
        _seed_pages(brain, ["alpha", "beta"])
        from llmwiki.workers.runner import JobWorker

        r = client.post("/api/index/reindex")
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        worker = JobWorker()
        worker.start()
        try:
            done = _wait_for_job(brain, job_id, "done", timeout=15.0)
            assert done["error"] is None
        finally:
            worker.stop()
            worker.join(timeout=5)

        # wiki_pages populated; status shows sync.
        conn = get_connection(brain.db_path)
        try:
            n_pages = conn.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0]
            meta_value = MetaRepo(conn).get("last_reindex_at")
        finally:
            conn.close()
        assert n_pages == 2
        assert meta_value is not None  # AC5: persisted

        # AC5: a fresh connection sees the same timestamp.
        conn2 = get_connection(brain.db_path)
        try:
            again = MetaRepo(conn2).get("last_reindex_at")
        finally:
            conn2.close()
        assert again == meta_value

        # Status reports it.
        body = client.get("/api/index/status").json()
        assert body["last_reindex_at"] == meta_value
        assert body["stale"] is False
        assert body["drift"] == 0

    def test_index_job_emits_sse_progress_and_result(
        self, client, brain: BrainPaths
    ) -> None:
        """SSE stream from the index job emits status events and a terminal done."""
        _seed_pages(brain, ["sse"])
        from llmwiki.workers.runner import JobWorker

        r = client.post("/api/index/reindex")
        job_id = r.json()["job_id"]

        worker = JobWorker()
        worker.start()
        try:
            _wait_for_job(brain, job_id, "done", timeout=15.0)
        finally:
            worker.stop()
            worker.join(timeout=5)

        r = client.get(f"/api/jobs/{job_id}/events")
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        assert "event: status" in r.text
        assert "event: result" in r.text
        assert "event: end" in r.text


class TestStatusSkipped:
    """#317: GET /index/status excludes skipped (malformed) pages from drift."""

    def test_malformed_page_not_counted_as_drift(
        self, client, brain: BrainPaths
    ) -> None:
        from llmwiki.core.config import load_config
        from llmwiki.services import index_service

        _seed_pages(brain, ["rag", "vectors"])  # 2 valid
        (brain.wiki / "concepts" / "broken.md").write_text(
            "---\n- not\n- a mapping\n---\nbody\n", encoding="utf-8"
        )
        conn = get_connection(brain.db_path)
        try:
            report = index_service.reindex(brain, conn, load_config(brain))
            index_service.rebuild_index_md(brain, conn)
        finally:
            conn.close()
        assert len(report.skipped) == 1

        body = client.get("/api/index/status").json()
        assert body["disk_files"] == 3
        assert body["db_pages"] == 2
        assert body["skipped"] == 1
        assert body["drift"] == 0
        assert body["stale"] is False
