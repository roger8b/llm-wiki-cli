from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core.errors import BrainNotFoundError, PathOutsideBrainError
from llmwiki.core.paths import (
    BrainPaths,
    find_brain_root,
    load_brain,
    resolve_input,
)


def _make_brain(root: Path) -> None:
    (root / ".llmwiki").mkdir(parents=True)
    (root / "wiki").mkdir()


class TestFindBrainRoot:
    def test_finds_in_current(self, tmp_path: Path) -> None:
        _make_brain(tmp_path)
        assert find_brain_root(tmp_path) == tmp_path

    def test_walks_up(self, tmp_path: Path) -> None:
        _make_brain(tmp_path)
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert find_brain_root(nested) == tmp_path

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert find_brain_root(tmp_path) is None

    def test_load_brain_raises_when_absent(self, tmp_path: Path) -> None:
        with pytest.raises(BrainNotFoundError):
            load_brain(tmp_path)


class TestResolveInput:
    def test_existing_relative_to_cwd(self, tmp_path: Path) -> None:
        _make_brain(tmp_path)
        f = tmp_path / "wiki" / "x.md"
        f.write_text("x")
        assert resolve_input(str(f), tmp_path) == f.resolve()

    def test_fallback_to_brain_root(self, tmp_path: Path) -> None:
        _make_brain(tmp_path)
        got = resolve_input("wiki/concepts/foo.md", tmp_path)
        assert got == (tmp_path / "wiki/concepts/foo.md").resolve()

    def test_rejects_path_outside_brain(self, tmp_path: Path) -> None:
        _make_brain(tmp_path)
        with pytest.raises(PathOutsideBrainError):
            resolve_input("/etc/passwd", tmp_path)


class TestBrainPaths:
    def test_derived_paths(self, tmp_path: Path) -> None:
        import llmwiki.core.paths as _paths_mod

        bp = BrainPaths(root=tmp_path)
        # db lives in the global home, under brains/<brain-name>/
        assert bp.db_path == _paths_mod.WIKI_HOME / "brains" / tmp_path.name / "metadata.db"
        assert bp.index_path == tmp_path / "wiki" / "index.md"

    def test_relative(self, tmp_path: Path) -> None:
        bp = BrainPaths(root=tmp_path)
        assert bp.relative(tmp_path / "wiki" / "a.md") == "wiki/a.md"
