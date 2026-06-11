"""Tests for the ExtractedSource contract + metadata pipeline (issue #163)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from llmwiki.llm_agents import factory
from llmwiki.sources.extractors import ExtractedSource, extract, extract_text
from llmwiki.sources.extractors import markdown as md_extractor

_HAS_TRAFILATURA = importlib.util.find_spec("trafilatura") is not None
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_markdown_extract_source_title_from_frontmatter(tmp_path: Path) -> None:
    doc = tmp_path / "a.md"
    doc.write_text("---\ntitle: My Title\n---\n# Heading\nbody\n", encoding="utf-8")
    src = md_extractor.extract_source(doc)
    assert isinstance(src, ExtractedSource)
    assert src.title == "My Title"
    assert "body" in src.text


def test_markdown_extract_source_title_from_h1(tmp_path: Path) -> None:
    doc = tmp_path / "b.md"
    doc.write_text("# Just an H1\n\nsome content\n", encoding="utf-8")
    assert md_extractor.extract_source(doc).title == "Just an H1"


def test_extract_returns_extracted_source_for_txt(tmp_path: Path) -> None:
    doc = tmp_path / "c.txt"
    doc.write_text("plain text no title", encoding="utf-8")
    src = extract(doc)
    assert isinstance(src, ExtractedSource)
    assert src.text == "plain text no title"


def test_extract_text_wrapper_still_works(tmp_path: Path) -> None:
    doc = tmp_path / "d.md"
    doc.write_text("# T\nhello world\n", encoding="utf-8")
    assert "hello world" in extract_text(doc)


def test_registry_normalizes_legacy_str() -> None:
    # The pdf extractor returns a plain str; extract() must wrap it.
    from llmwiki.sources import extractors

    def fake_str_extractor(path: Path) -> str:
        return "legacy text"

    original = extractors._REGISTRY.get(".md")
    extractors._REGISTRY[".md"] = fake_str_extractor
    try:
        src = extract(Path("whatever.md"))
        assert isinstance(src, ExtractedSource)
        assert src.text == "legacy text"
        assert src.title is None
    finally:
        assert original is not None
        extractors._REGISTRY[".md"] = original


class TestMetadataLine:
    def test_only_present_fields(self) -> None:
        line = factory._metadata_line(
            {"title": "RAG", "author": None, "date": "2026-01-15", "url": None}
        )
        assert "título=RAG" in line
        assert "data=2026-01-15" in line
        assert "autor" not in line
        assert "url" not in line

    def test_empty_meta_yields_empty_string(self) -> None:
        assert factory._metadata_line(None) == ""
        assert factory._metadata_line({"title": None}) == ""


def test_ingest_passes_source_meta_to_runner(tmp_path: Path) -> None:
    from llmwiki.core.config import WorkspaceConfig
    from llmwiki.db.connection import get_connection
    from llmwiki.llm_agents.models import IngestionResult
    from llmwiki.services import ingest_service, scaffold_service

    brain = scaffold_service.init_brain(tmp_path / "brain", git=False)
    src = brain.raw / "articles" / "a.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("---\ntitle: Source Title\n---\n# H\nbody text here\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def runner(cfg, backend, *, source_path, source_text, source_meta=None):
        captured["meta"] = source_meta
        return IngestionResult(summary="ok")

    cfg = WorkspaceConfig(brain_root=brain.root)
    conn = get_connection(brain.db_path)
    try:
        ingest_service.ingest(src, brain, conn, cfg, runner=runner)
    finally:
        conn.close()
    assert captured["meta"]["title"] == "Source Title"  # type: ignore[index]


@pytest.mark.skipif(not _HAS_TRAFILATURA, reason="trafilatura not installed ([html] extra)")
def test_html_extract_source_carries_metadata() -> None:
    src = extract(_FIXTURES / "sample_article.html")
    assert src.title == "Retrieval-Augmented Generation"
    assert src.author == "Jane Researcher"
    assert "Retrieval-augmented generation grounds" in src.text
