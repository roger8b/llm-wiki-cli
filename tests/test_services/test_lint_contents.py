"""Unit tests for in-memory content lint (#166)."""

from __future__ import annotations

from llmwiki.services import lint_service


def _kinds(files: dict[str, str], known: dict[str, str]) -> list[str]:
    return [f.kind for f in lint_service.lint_contents(files, known_titles=known)]


def test_invalid_frontmatter() -> None:
    files = {"wiki/concepts/a.md": "---\ntitle: : :\n  - x\n---\nbody"}
    kinds = _kinds(files, lint_service.titles_from_contents(files))
    assert "invalid_frontmatter" in kinds


def test_missing_frontmatter() -> None:
    files = {"wiki/concepts/a.md": "# No frontmatter\nbody\n"}
    assert "missing_frontmatter" in _kinds(files, lint_service.titles_from_contents(files))


def test_invalid_page_type() -> None:
    files = {"wiki/concepts/a.md": "---\ntitle: A\ntype: bogus\n---\n# A\n"}
    assert "invalid_page_type" in _kinds(files, lint_service.titles_from_contents(files))


def test_broken_link_against_known_titles() -> None:
    files = {"wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n[[Nope]]\n"}
    known = lint_service.titles_from_contents(files)
    assert "broken_link" in _kinds(files, known)


def test_link_to_sibling_in_same_staging_is_not_broken() -> None:
    # A new page linking to another new page created in the same run resolves
    # because known_titles includes the staging titles.
    files = {
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n[[B]]\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n# B\n",
    }
    known = lint_service.titles_from_contents(files)
    assert "broken_link" not in _kinds(files, known)


def test_no_orphan_check_in_contents() -> None:
    # A standalone page with no incoming links is NOT flagged here (orphan is a
    # disk-only, post-run concern).
    files = {"wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n# A\n"}
    assert "orphan_page" not in _kinds(files, lint_service.titles_from_contents(files))


def test_clean_page_has_no_findings() -> None:
    files = {"wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n# A\nbody\n"}
    assert _kinds(files, lint_service.titles_from_contents(files)) == []
