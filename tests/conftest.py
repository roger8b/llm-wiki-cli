"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

import llmwiki.core.paths as _paths_module
from llmwiki.core.paths import BrainPaths
from llmwiki.services import scaffold_service


@pytest.fixture(autouse=True)
def isolated_wiki_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect WIKI_HOME to a temp dir so tests never touch ~/.wiki.

    Patching the module attribute means both ``llmwiki.core.paths.WIKI_HOME``
    and the ``_paths_module.WIKI_HOME`` reference inside ``config.py`` see the
    same value.
    """
    fake_home = tmp_path / "_wiki_home"
    fake_home.mkdir()
    monkeypatch.setattr(_paths_module, "WIKI_HOME", fake_home)
    return fake_home


@pytest.fixture
def brain(tmp_path: Path) -> BrainPaths:
    """Create an isolated brain in tmp_path (no git)."""
    return scaffold_service.init_brain(tmp_path / "brain", git=False)
