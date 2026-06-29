"""API tests for DELETE /api/sources (#310) — non-ingested sources only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import SourceRepo
from llmwiki.sources.manager import add_source


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _make_pending_source(brain: BrainPaths, name: str = "x.md", content: str = "x") -> str:
    """Drop a pending source on disk + DB; return its relative path."""
    src = brain.root / "tmp_upload.md"
    src.write_text(content, encoding="utf-8")
    conn = get_connection(brain.db_path)
    try:
        result = add_source(src, brain, SourceRepo(conn))
    finally:
        conn.close()
    src.unlink(missing_ok=True)
    return result.source.path


class TestDeleteSource:
    def test_delete_pending_removes_from_next_list(
        self, client: TestClient, brain: BrainPaths
    ) -> None:
        path = _make_pending_source(brain, "delete-me.md", "unique content")
        # Sanity: listed before delete.
        before = client.get("/api/sources").json()
        assert any(s["path"] == path for s in before)

        r = client.request("DELETE", "/api/sources", json={"path": path})
        assert r.status_code == 200, r.text

        after = client.get("/api/sources").json()
        assert not any(s["path"] == path for s in after)

    def test_delete_processed_returns_409(
        self, client: TestClient, brain: BrainPaths
    ) -> None:
        path = _make_pending_source(brain, "ingested.md", "already processed")
        conn = get_connection(brain.db_path)
        try:
            SourceRepo(conn).mark_processed(path)
        finally:
            conn.close()

        r = client.request("DELETE", "/api/sources", json={"path": path})
        assert r.status_code == 409, r.text

    def test_delete_missing_returns_404(
        self, client: TestClient, brain: BrainPaths
    ) -> None:
        r = client.request(
            "DELETE", "/api/sources", json={"path": "raw/never-existed.md"}
        )
        assert r.status_code == 404, r.text

    def test_delete_traversal_returns_400(
        self, client: TestClient, brain: BrainPaths
    ) -> None:
        r = client.request(
            "DELETE", "/api/sources", json={"path": "../etc/passwd"}
        )
        assert r.status_code == 400, r.text

    def test_delete_requires_path(self, client: TestClient) -> None:
        # FastAPI's body validation returns 422 (Unprocessable Entity) for a
        # missing required field — the HTTP-correct answer. The 400 path is
        # reserved for traversal (escape-the-brain) errors.
        r = client.request("DELETE", "/api/sources", json={})
        assert r.status_code == 422, r.text
