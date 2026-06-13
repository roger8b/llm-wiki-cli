"""API partial apply: POST /change-requests/{id}/apply with a paths subset (#184)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.models import FileChange
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import change_request_service as crs


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _make_cr(brain: BrainPaths, names: list[str]) -> str:
    changes = [
        FileChange(
            path=f"wiki/concepts/{n}.md",
            operation="create",
            new_content=f"---\ntitle: {n}\ntype: concept\n---\n# {n}\nBody.\n",
            diff=f"+{n}",
        )
        for n in names
    ]
    conn = get_connection(brain.db_path)
    try:
        return crs.create_from_changes(changes, "multi", brain, conn).id
    finally:
        conn.close()


def test_partial_apply_settles_cr(client, brain: BrainPaths) -> None:
    cr_id = _make_cr(brain, ["a", "b", "c"])
    r = client.post(
        f"/api/change-requests/{cr_id}/apply",
        json={"paths": ["wiki/concepts/a.md"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "applied"
    assert body["applied_paths"] == ["wiki/concepts/a.md"]
    assert set(body["rejected_paths"]) == {"wiki/concepts/b.md", "wiki/concepts/c.md"}
    assert (brain.root / "wiki/concepts/a.md").exists()
    assert not (brain.root / "wiki/concepts/b.md").exists()


def test_unknown_path_400(client, brain: BrainPaths) -> None:
    cr_id = _make_cr(brain, ["a"])
    r = client.post(
        f"/api/change-requests/{cr_id}/apply", json={"paths": ["wiki/concepts/x.md"]}
    )
    assert r.status_code == 400


def test_empty_paths_400(client, brain: BrainPaths) -> None:
    cr_id = _make_cr(brain, ["a"])
    r = client.post(f"/api/change-requests/{cr_id}/apply", json={"paths": []})
    assert r.status_code == 400


def test_no_body_applies_all(client, brain: BrainPaths) -> None:
    cr_id = _make_cr(brain, ["a", "b"])
    r = client.post(f"/api/change-requests/{cr_id}/apply", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "applied"
    assert (brain.root / "wiki/concepts/a.md").exists()
    assert (brain.root / "wiki/concepts/b.md").exists()
