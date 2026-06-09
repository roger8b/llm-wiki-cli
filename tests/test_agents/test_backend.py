from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.llm_agents.backend import ChangeRequestBackend


@pytest.fixture
def brain_root(tmp_path: Path) -> Path:
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "raw" / "articles").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts" / "rag.md").write_text(
        "---\ntitle: RAG\n---\n# RAG\nconteúdo antigo\n", encoding="utf-8"
    )
    return tmp_path


class TestWriteCapture:
    def test_write_does_not_touch_disk(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("wiki/concepts/novo.md", "# Novo\n")
        assert res.error is None
        # nada gravado em disco
        assert not (brain_root / "wiki/concepts/novo.md").exists()
        # mas está no staging
        assert be.staging["wiki/concepts/novo.md"] == "# Novo\n"

    def test_write_to_raw_is_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("raw/articles/x.md", "hack")
        assert res.error is not None
        assert "raw/" in res.error
        assert "raw/articles/x.md" not in be.staging

    def test_path_traversal_is_blocked(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.write("../../etc/evil.md", "hack")
        assert res.error is not None
        assert be.staging == {}


class TestEdit:
    def test_edit_existing_from_disk(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.edit("wiki/concepts/rag.md", "conteúdo antigo", "conteúdo novo")
        assert res.error is None
        assert res.occurrences == 1
        assert "conteúdo novo" in be.staging["wiki/concepts/rag.md"]
        assert not (brain_root / "wiki/concepts/rag.md").read_text().count("novo")

    def test_edit_missing_file(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        assert be.edit("wiki/concepts/nope.md", "a", "b").error is not None

    def test_edit_ambiguous_without_replace_all(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/dup.md", "x x x")
        res = be.edit("wiki/concepts/dup.md", "x", "y")
        assert res.error is not None

    def test_edit_replace_all(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/dup.md", "x x x")
        res = be.edit("wiki/concepts/dup.md", "x", "y", replace_all=True)
        assert res.occurrences == 3
        assert be.staging["wiki/concepts/dup.md"] == "y y y"


class TestReadOverlay:
    def test_read_staged_content(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/novo.md", "linha staged\n")
        res = be.read("wiki/concepts/novo.md")
        assert res.error is None
        assert res.file_data is not None
        assert "linha staged" in res.file_data["content"]

    def test_read_disk_when_not_staged(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        res = be.read("wiki/concepts/rag.md")
        assert res.file_data is not None
        assert "conteúdo antigo" in res.file_data["content"]


class TestCollectChanges:
    def test_create_and_update(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        be.write("wiki/concepts/novo.md", "# Novo\n")
        be.edit("wiki/concepts/rag.md", "conteúdo antigo", "conteúdo novo")
        changes = {c.path: c for c in be.collect_changes()}
        assert changes["wiki/concepts/novo.md"].operation == "create"
        assert changes["wiki/concepts/rag.md"].operation == "update"
        assert changes["wiki/concepts/novo.md"].diff
        assert "conteúdo novo" in changes["wiki/concepts/rag.md"].diff

    def test_no_change_when_content_identical(self, brain_root: Path) -> None:
        be = ChangeRequestBackend(brain_root)
        # reescreve com o conteúdo idêntico ao do disco
        same = (brain_root / "wiki/concepts/rag.md").read_text(encoding="utf-8")
        be.write("wiki/concepts/rag.md", same)
        assert be.collect_changes() == []
