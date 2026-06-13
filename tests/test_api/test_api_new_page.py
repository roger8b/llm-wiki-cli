"""API: GET /wiki/templates + create collision via propose-edit (#187)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def test_templates_listed(client) -> None:
    r = client.get("/api/wiki/templates")
    assert r.status_code == 200
    types = {t["type"] for t in r.json()}
    assert "decision" in types and "concept" in types
    decision = next(t for t in r.json() if t["type"] == "decision")
    assert "{{title}}" in decision["body"]


def test_create_new_page_cr(client, brain: BrainPaths) -> None:
    r = client.post(
        "/api/wiki/pages/wiki/decisions/use-sqlite-vec.md/propose-edit",
        json={
            "frontmatter": {"title": "Use sqlite-vec", "type": "decision"},
            "body": "# Use sqlite-vec\nBody.\n",
            "expect_new": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["change_request_id"]


def test_collision_409(client, brain: BrainPaths) -> None:
    page = brain.wiki / "decisions" / "x.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\ntitle: X\ntype: decision\n---\n# X\n", encoding="utf-8")
    r = client.post(
        "/api/wiki/pages/wiki/decisions/x.md/propose-edit",
        json={
            "frontmatter": {"title": "X", "type": "decision"},
            "body": "# X\nnew\n",
            "expect_new": True,
        },
    )
    assert r.status_code == 409
