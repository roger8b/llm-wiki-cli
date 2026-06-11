"""Tests for the HTML extractor (issue #161)."""

from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

import pytest

from llmwiki.core.errors import EmptyExtractionError, ExtractorUnavailableError
from llmwiki.sources.extractors import extract_text
from llmwiki.sources.extractors import html as html_extractor

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Parsing needs the optional [html] extra; the core must work without it.
_HAS_TRAFILATURA = importlib.util.find_spec("trafilatura") is not None
requires_trafilatura = pytest.mark.skipif(
    not _HAS_TRAFILATURA, reason="trafilatura not installed (the [html] extra)"
)


@requires_trafilatura
def test_strips_boilerplate_keeps_article() -> None:
    text = html_extractor.extract(_FIXTURES / "sample_article.html")
    assert "Retrieval-augmented generation grounds" in text
    assert "vector database" in text
    # Boilerplate must be gone.
    assert "SITE BANNER" not in text
    assert "Copyright 2026" not in text
    assert "tracking pixel" not in text
    assert "Newsletter" not in text


@requires_trafilatura
def test_links_preserved_as_markdown() -> None:
    text = html_extractor.extract(_FIXTURES / "sample_article.html")
    assert "https://example.com/vector-db" in text


@requires_trafilatura
def test_extract_text_dispatches_to_html(tmp_path: Path) -> None:
    doc = tmp_path / "x.html"
    doc.write_text(
        "<html><body><article><h1>Title</h1>"
        "<p>" + ("Substantial article body content here. " * 10) + "</p>"
        "</article></body></html>",
        encoding="utf-8",
    )
    assert "Substantial article body content" in extract_text(doc)


@requires_trafilatura
def test_metadata_captured() -> None:
    meta = html_extractor.extract_metadata(_FIXTURES / "sample_article.html")
    assert meta["title"] == "Retrieval-Augmented Generation"
    assert meta["author"] == "Jane Researcher"
    assert meta["date"] == "2026-01-15"


@requires_trafilatura
def test_empty_html_raises(tmp_path: Path) -> None:
    doc = tmp_path / "empty.html"
    # No main content — only scripts/styles (e.g. a JS-rendered shell or paywall).
    doc.write_text(
        "<html><head><title>x</title></head><body>"
        "<script>var a=1;</script><style>.x{color:red}</style></body></html>",
        encoding="utf-8",
    )
    with pytest.raises(EmptyExtractionError):
        html_extractor.extract(doc)


def test_missing_trafilatura_raises_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "x.html"
    doc.write_text("<html><body><p>hi</p></body></html>", encoding="utf-8")
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "trafilatura":
            raise ImportError("No module named 'trafilatura'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ExtractorUnavailableError, match=r"llm-wiki\[html\]"):
        html_extractor.extract(doc)
