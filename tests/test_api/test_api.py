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
        client.get("/api/graph")
        r = client.get("/api/wiki/pages")
        assert r.status_code == 200
        assert any(p["title"] == "RAG" for p in r.json())

    def test_get_page_content(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        r = client.get("/api/wiki/pages/wiki/concepts/rag.md")
        assert r.status_code == 200
        assert r.json()["frontmatter"]["title"] == "RAG"

    def test_get_missing_page_404(self, client) -> None:
        assert client.get("/api/wiki/pages/wiki/nope.md").status_code == 404

    def test_search(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        client.get("/api/graph")  # reindexa (popula FTS)
        r = client.get("/api/search", params={"q": "retrieval"})
        assert r.status_code == 200
        assert r.json()[0]["path"].endswith("rag.md")

    def test_lint_structural(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        r = client.post("/api/lint", json={"semantic": False})
        assert r.status_code == 200
        assert "findings" in r.json()

    def test_review_ui_served(self, client) -> None:
        # GET / serves the built SPA (index.html with #root) when dist/ exists,
        # otherwise falls back to the legacy review.html. Accept either.
        r = client.get("/")
        assert r.status_code == 200
        text = r.text.lower()
        assert "<!doctype html" in text or "<html" in text
        assert 'id="root"' in r.text or "Review Changes" in r.text


class TestChangeRequestsEndpoints:
    def test_empty_list(self, client) -> None:
        r = client.get("/api/change-requests")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_missing_cr_404(self, client) -> None:
        assert client.get("/api/change-requests/CR-2026-9999").status_code == 404


class TestConfigEndpoints:
    def test_get_config(self, client) -> None:
        r = client.get("/api/config")
        assert r.status_code == 200
        body = r.json()
        assert "model" in body and "fts_limit" in body

    def test_patch_config(self, client) -> None:
        r = client.patch("/api/config", json={"model": "anthropic:claude-sonnet-4-5"})
        assert r.status_code == 200
        assert r.json()["model"] == "anthropic:claude-sonnet-4-5"
        assert client.get("/api/config").json()["model"] == "anthropic:claude-sonnet-4-5"

    def test_patch_config_partial(self, client) -> None:
        client.patch("/api/config", json={"fts_limit": 42})
        assert client.get("/api/config").json()["fts_limit"] == 42


class TestSourceMutations:
    def test_add_text_source(self, client) -> None:
        r = client.post(
            "/api/sources/text",
            json={"title": "My Note", "content": "Some body text."},
        )
        assert r.status_code == 200
        assert r.json()["path"].endswith("my-note.md")
        paths = [s["path"] for s in client.get("/api/sources").json()]
        assert any(p.endswith("my-note.md") for p in paths)

    def test_upload_source(self, client) -> None:
        r = client.post(
            "/api/sources/upload",
            files={"file": ("note.md", b"# Uploaded\nbody", "text/markdown")},
        )
        assert r.status_code == 200
        assert r.json()["path"].endswith("note.md")


class TestBrainsEndpoint:
    def test_list_brains(self, client) -> None:
        r = client.get("/api/brains")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestHealth:
    def test_health_ok(self, client) -> None:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestSetupEndpoints:
    def test_onboarding_status(self, client) -> None:
        r = client.get("/api/onboarding")
        assert r.status_code == 200
        body = r.json()
        assert "needs_onboarding" in body and "ollama" in body

    def test_cli_status_shape(self, client) -> None:
        r = client.get("/api/cli")
        assert r.status_code == 200
        body = r.json()
        for key in ("installed", "path", "on_path", "version"):
            assert key in body

    def test_config_test_unknown_provider(self, client) -> None:
        r = client.post("/api/config/test", json={"model": "bogus:x"})
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestSpaRouting:
    """SPA client routes must not collide with API routes."""

    def test_spa_route_does_not_return_json_list(self, client) -> None:
        # /sources is both an API path (/api/sources) and an SPA client route.
        # The bare /sources must NEVER return the JSON source list. When the SPA
        # is built it returns index.html (200); without a build it 404s. Either
        # is fine — what matters is it's not the API JSON.
        r = client.get("/sources")
        if r.status_code == 200:
            assert "text/html" in r.headers["content-type"]
        else:
            assert r.status_code == 404

    def test_api_sources_returns_json(self, client) -> None:
        r = client.get("/api/sources")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_brain_not_found_returns_404(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WIKI_BRAIN", str(tmp_path / "nope"))
    from llmwiki.interfaces.api.main import app

    c = TestClient(app)
    assert c.get("/api/sources").status_code == 404
