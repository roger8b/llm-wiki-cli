"""Tests for the per-page quality heuristic (issue #168)."""

from __future__ import annotations

from llmwiki.core.quality import assess_page

_BODY = " ".join(["word"] * 200)


def _page(
    *,
    title: str = "RAG",
    ptype: str = "concept",
    tags: str = "[rag]",
    sources: str = "[raw/articles/x.md]",
    updated_at: str = "2026-06-10",
    confidence: str = "high",
    body: str = "",
) -> str:
    fm = (
        f"---\ntitle: {title}\ntype: {ptype}\ntags: {tags}\n"
        f"sources: {sources}\nupdated_at: {updated_at}\nconfidence: {confidence}\n---\n"
    )
    return fm + body


def test_exemplary_page_scores_high() -> None:
    content = _page(
        body=f"# RAG\n\n## Definition\n{_BODY}\n\nSee [[Vector Database]].\n"
    )
    report = assess_page(content, known_titles={"vector-database"})
    assert report.score >= 90
    assert report.flags == []


def test_short_page_without_links_scores_low() -> None:
    content = _page(
        sources="[]",
        body="# Stub\n" + " ".join(["w"] * 50),
    )
    report = assess_page(content)
    assert report.score < 50
    assert "short_body" in report.flags
    assert "no_links" in report.flags
    assert "no_sections" in report.flags
    assert "no_sources" in report.flags


def test_unresolved_link_flagged_when_titles_known() -> None:
    content = _page(body=f"# RAG\n\n## D\n{_BODY}\n[[Nonexistent Page]]\n")
    report = assess_page(content, known_titles={"vector-database"})
    assert "unresolved_links" in report.flags


def test_link_counts_without_known_titles() -> None:
    content = _page(body=f"# RAG\n\n## D\n{_BODY}\n[[Anything]]\n")
    report = assess_page(content)  # no known_titles → presence is enough
    assert "no_links" not in report.flags
    assert "unresolved_links" not in report.flags


def test_incomplete_frontmatter_flagged() -> None:
    content = "---\ntitle: X\ntype: concept\n---\n# X\n\n## S\n" + _BODY
    report = assess_page(content)
    assert "incomplete_frontmatter" in report.flags
