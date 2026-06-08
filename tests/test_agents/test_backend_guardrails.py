"""Tests for the write guardrails added in epic #118.

Covers the allow-list (wiki/ only), generated-file protection, extension policy,
read-only mode auditing, and the staging overlay for ls/grep/glob.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.agents.backend import ChangeRequestBackend, validate_change_path


@pytest.fixture
def brain_root(tmp_path: Path) -> Path:
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "raw" / "articles").mkdir(parents=True)
    (tmp_path / ".llmwiki").mkdir()
    (tmp_path / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
    (tmp_path / "wiki" / "concepts" / "rag.md").write_text(
        "---\ntitle: RAG\n---\n# RAG\nold body\n", encoding="utf-8"
    )
    return tmp_path


class TestAllowList:
    def test_write_under_wiki_md_is_allowed(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        assert be.write("wiki/concepts/novo.md", "# Novo\n").error is None
        assert "wiki/concepts/novo.md" in be.staging

    def test_write_outside_wiki_is_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("notes.md", "x")
        assert res.error is not None
        assert "wiki/" in res.error
        assert be.staging == {}

    def test_write_to_llmwiki_is_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write(".llmwiki/config.toml", "evil = true")
        assert res.error is not None
        assert be.staging == {}

    def test_write_to_raw_is_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("raw/articles/x.md", "hack")
        assert res.error is not None
        assert "raw/" in res.error
        assert be.staging == {}


class TestGeneratedFiles:
    def test_write_index_md_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("wiki/index.md", "# tampered\n")
        assert res.error is not None
        assert "generated" in res.error
        assert be.staging == {}

    def test_edit_log_md_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.edit("wiki/log.md", "a", "b")
        assert res.error is not None


class TestExtensionPolicy:
    def test_non_md_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("wiki/data.json", "{}")
        assert res.error is not None
        assert ".md" in res.error
        assert be.staging == {}


class TestReadOnlyMode:
    def test_write_blocked_and_recorded(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root, read_only=True)
        res = be.write("wiki/concepts/novo.md", "# Novo\n")
        assert res.error is not None
        assert "read-only" in res.error
        assert be.staging == {}
        assert be.write_attempts == ["wiki/concepts/novo.md"]

    def test_edit_blocked_and_recorded(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root, read_only=True)
        res = be.edit("wiki/concepts/rag.md", "old body", "new body")
        assert res.error is not None
        assert be.write_attempts == ["wiki/concepts/rag.md"]
        # disk untouched
        assert "old body" in (brain_root / "wiki/concepts/rag.md").read_text()


class TestStagingOverlay:
    def test_grep_sees_staged_content(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/vector.md", "---\ntitle: Vector\n---\nVector store concept\n")
        res = be.grep("Vector store", path="wiki")
        assert res.matches is not None
        paths = {m["path"] for m in res.matches}
        assert "/wiki/concepts/vector.md" in paths

    def test_glob_sees_staged_file(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/vector.md", "x\n")
        res = be.glob("*.md", path="wiki/concepts")
        assert res.matches is not None
        paths = {m["path"] for m in res.matches}
        assert "/wiki/concepts/vector.md" in paths

    def test_ls_sees_staged_file(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/vector.md", "x\n")
        res = be.ls("wiki/concepts")
        assert res.entries is not None
        paths = {e["path"] for e in res.entries}
        assert "/wiki/concepts/vector.md" in paths

    def test_grep_overlay_reflects_edit_not_stale_disk(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.edit("wiki/concepts/rag.md", "old body", "fresh body")
        res = be.grep("fresh body", path="wiki")
        assert res.matches is not None
        assert any(m["path"] == "/wiki/concepts/rag.md" for m in res.matches)
        # the stale disk line must not surface
        stale = be.grep("old body", path="wiki")
        assert all(m["path"] != "/wiki/concepts/rag.md" for m in (stale.matches or []))


class TestValidateChangePath:
    @pytest.mark.parametrize(
        "path",
        ["wiki/concepts/ok.md", "wiki/decisions/x.md"],
    )
    def test_valid(self, path: str) -> None:
        assert validate_change_path(path) is None

    @pytest.mark.parametrize(
        "path",
        [
            "raw/x.md",
            ".llmwiki/config.toml",
            "notes.md",
            "wiki/index.md",
            "wiki/log.md",
            "wiki/data.json",
            "wiki/../escape.md",
        ],
    )
    def test_invalid(self, path: str) -> None:
        assert validate_change_path(path) is not None
