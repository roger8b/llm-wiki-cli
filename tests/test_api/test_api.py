from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _seed_page(brain: BrainPaths) -> None:
    p = brain.wiki / "concepts" / "rag.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: RAG\ntype: concept\n---\n# RAG\nretrieval\n", encoding="utf-8")


class TestReadEndpoints:
    def test_list_pages_after_index(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        # popula índice via endpoint graph (que reindexa) ou search
        client.get("/graph")
        r = client.get("/wiki/pages")
        assert r.status_code == 200
        assert any(p["title"] == "RAG" for p in r.json())

    def test_get_page_content(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        r = client.get("/wiki/pages/wiki/concepts/rag.md")
        assert r.status_code == 200
        assert r.json()["frontmatter"]["title"] == "RAG"

    def test_get_missing_page_404(self, client) -> None:
        assert client.get("/wiki/pages/wiki/nope.md").status_code == 404

    def test_search(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        client.get("/graph")  # reindexa (popula FTS)
        r = client.get("/search", params={"q": "retrieval"})
        assert r.status_code == 200
        assert r.json()[0]["path"].endswith("rag.md")

    def test_lint_structural(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        r = client.post("/lint", json={"semantic": False})
        assert r.status_code == 200
        assert "findings" in r.json()

    def test_review_ui_served(self, client) -> None:
        r = client.get("/")
        assert r.status_code == 200
        assert "Review Changes" in r.text


class TestChangeRequestsEndpoints:
    def test_empty_list(self, client) -> None:
        r = client.get("/change-requests")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_missing_cr_404(self, client) -> None:
        assert client.get("/change-requests/CR-2026-9999").status_code == 404


def test_brain_not_found_returns_404(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WIKI_BRAIN", str(tmp_path / "nope"))
    from llmwiki.interfaces.api.main import app

    c = TestClient(app)
    assert c.get("/sources").status_code == 404
