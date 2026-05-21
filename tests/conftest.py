"""Fixtures compartilhadas."""

from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core.paths import BrainPaths
from llmwiki.services import scaffold_service


@pytest.fixture
def brain(tmp_path: Path) -> BrainPaths:
    """Cria um brain isolado em tmp_path (sem git)."""
    return scaffold_service.init_brain(tmp_path / "brain", git=False)
