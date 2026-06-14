"""URL ingestion (#195): add_url + /sources/url with trafilatura mocked."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from llmwiki.core import frontmatter
from llmwiki.core.errors import EmptyExtractionError, FetchError
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import SourceRepo
from llmwiki.sources import manager


class FakeTrafilatura:
    """Stand-in for the trafilatura module used by the extractor + fetcher."""

    def __init__(self, html: str | None, text: str, meta: dict[str, Any]) -> None:
        self._html = html
        self._text = text
        self._meta = meta

    def fetch_url(self, url: str, config: Any = None) -> str | None:  # noqa: ARG002
        return self._html

    def extract(self, html: str, **_: Any) -> str | None:  # noqa: ARG002
        return self._text

    def extract_metadata(self, html: str) -> Any:  # noqa: ARG002
        return SimpleNamespace(**self._meta)


def _patch(monkeypatch: pytest.MonkeyPatch, fake: FakeTrafilatura) -> None:
    monkeypatch.setattr(
        "llmwiki.sources.extractors.html._load_trafilatura", lambda: fake
    )


ARTICLE = "Some genuinely long extracted article body. " * 10


class TestAddUrl:
    def test_success_writes_web_file_with_capture_frontmatter(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(
            monkeypatch,
            FakeTrafilatura(
                "<html>…</html>",
                ARTICLE,
                {"title": "Great Article", "author": "Jane", "date": "2026-01-02"},
            ),
        )
        conn = get_connection(brain.db_path)
        try:
            result = manager.add_url(
                "https://example.com/post", brain, SourceRepo(conn)
            )
        finally:
            conn.close()
        assert result.copied is True
        assert result.already_present is False
        assert result.source.path == "raw/web/great-article.md"
        assert result.source.title == "Great Article"
        dest = brain.raw / "web" / "great-article.md"
        meta, body = frontmatter.parse(dest.read_text(encoding="utf-8"))
        assert meta["url"] == "https://example.com/post"
        assert meta["author"] == "Jane"
        assert meta["date"] == "2026-01-02"
        assert "captured_at" in meta
        assert body.strip().startswith("Some genuinely long")

    def test_rejects_non_http_scheme(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, FakeTrafilatura("x", ARTICLE, {}))
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(FetchError):
                manager.add_url("ftp://example.com/x", brain, SourceRepo(conn))
        finally:
            conn.close()

    def test_download_failure_raises_fetch_error(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, FakeTrafilatura(None, ARTICLE, {}))  # 404/timeout
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(FetchError):
                manager.add_url("https://example.com/404", brain, SourceRepo(conn))
        finally:
            conn.close()

    def test_thin_extraction_raises_empty(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, FakeTrafilatura("<html>", "tiny", {"title": "T"}))
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(EmptyExtractionError):
                manager.add_url("https://example.com/paywall", brain, SourceRepo(conn))
        finally:
            conn.close()

    def test_recapture_same_content_is_duplicate(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(
            monkeypatch, FakeTrafilatura("<html>", ARTICLE, {"title": "Dup Article"})
        )
        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            manager.add_url("https://example.com/a", brain, repo)
            again = manager.add_url("https://example.com/a", brain, repo)
        finally:
            conn.close()
        assert again.already_present is True

    def test_collision_suffixes_filename(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            _patch(
                monkeypatch,
                FakeTrafilatura("<html>", ARTICLE + " one", {"title": "Same Title"}),
            )
            manager.add_url("https://example.com/1", brain, repo)
            _patch(
                monkeypatch,
                FakeTrafilatura("<html>", ARTICLE + " two", {"title": "Same Title"}),
            )
            second = manager.add_url("https://example.com/2", brain, repo)
        finally:
            conn.close()
        assert second.source.path == "raw/web/same-title-2.md"
