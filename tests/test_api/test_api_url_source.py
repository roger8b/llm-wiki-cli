"""API tests for URL ingestion endpoints (#195), trafilatura mocked."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


class _Fake:
    def __init__(self, html: str | None, text: str, meta: dict[str, Any]) -> None:
        self._html, self._text, self._meta = html, text, meta

    def fetch_url(self, url: str, config: Any = None) -> str | None:  # noqa: ARG002
        return self._html

    def extract(self, html: str, **_: Any) -> str | None:  # noqa: ARG002
        return self._text

    def extract_metadata(self, html: str) -> Any:  # noqa: ARG002
        return SimpleNamespace(**self._meta)


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _Fake) -> None:
    monkeypatch.setattr(
        "llmwiki.sources.extractors.html._load_trafilatura", lambda: fake
    )


BODY = "A sufficiently long article body for extraction. " * 8


class TestUrlEndpoints:
    def test_add_url_success(self, client, monkeypatch) -> None:
        _patch(monkeypatch, _Fake("<html>", BODY, {"title": "Hello Web"}))
        r = client.post("/api/sources/url", json={"url": "https://ex.com/p"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["title"] == "Hello Web"
        assert data["path"] == "raw/web/hello-web.md"
        assert data["already_present"] is False

    def test_add_url_duplicate(self, client, monkeypatch) -> None:
        _patch(monkeypatch, _Fake("<html>", BODY, {"title": "Dup"}))
        client.post("/api/sources/url", json={"url": "https://ex.com/a"})
        r = client.post("/api/sources/url", json={"url": "https://ex.com/a"})
        assert r.status_code == 200
        assert r.json()["already_present"] is True

    def test_add_url_404_is_502(self, client, monkeypatch) -> None:
        _patch(monkeypatch, _Fake(None, BODY, {}))
        r = client.post("/api/sources/url", json={"url": "https://ex.com/404"})
        assert r.status_code == 502

    def test_add_url_empty_is_422(self, client, monkeypatch) -> None:
        _patch(monkeypatch, _Fake("<html>", "thin", {"title": "T"}))
        r = client.post("/api/sources/url", json={"url": "https://ex.com/paywall"})
        assert r.status_code == 422

    def test_preview_returns_title_and_snippet(self, client, monkeypatch) -> None:
        _patch(monkeypatch, _Fake("<html>", BODY, {"title": "Preview Me"}))
        r = client.post("/api/sources/url/preview", json={"url": "https://ex.com/x"})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Preview Me"
        assert data["preview"].startswith("A sufficiently long")
        # preview must not have persisted a source
        assert client.get("/api/sources").json() == []
