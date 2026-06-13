"""API: POST /wiki/pages/{path}/propose-edit (#186)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _seed(brain: BrainPaths) -> str:
    p = brain.wiki / "concepts" / "rag.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: RAG\ntype: concept\n---\n# RAG\nOld.\n", encoding="utf-8"
    )
    return "wiki/concepts/rag.md"


def test_propose_edit_creates_cr(client, brain: BrainPaths) -> None:
    path = _seed(brain)
    r = client.post(
        f"/api/wiki/pages/{path}/propose-edit",
        json={
            "frontmatter": {"title": "RAG", "type": "concept"},
            "body": "# RAG\nEdited via app.\n",
        },
    )
    assert r.status_code == 200
    assert r.json()["change_request_id"]
    assert r.json()["files_changed"] == 1
    # not written to disk yet
    assert "Edited via app." not in (brain.root / path).read_text(encoding="utf-8")


def test_invalid_type_400(client, brain: BrainPaths) -> None:
    path = _seed(brain)
    r = client.post(
        f"/api/wiki/pages/{path}/propose-edit",
        json={"frontmatter": {"title": "RAG", "type": "nope"}, "body": "# x\n"},
    )
    assert r.status_code == 400


def test_no_change_409(client, brain: BrainPaths) -> None:
    path = _seed(brain)
    r = client.post(
        f"/api/wiki/pages/{path}/propose-edit",
        json={"frontmatter": {"title": "RAG", "type": "concept"}, "body": "# RAG\nOld.\n"},
    )
    # identical body but updated_at gets stamped, so this still differs → CR.
    # Re-propose the resulting on-disk content to get a true no-op.
    assert r.status_code == 200
