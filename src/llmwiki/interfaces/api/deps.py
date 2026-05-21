"""Resolução de contexto (brain + config) para a API.

A raiz do brain vem da env ``WIKI_BRAIN`` ou da descoberta a partir do cwd.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ...core.config import WorkspaceConfig, load_config
from ...core.errors import BrainNotFoundError
from ...core.paths import BrainPaths, find_brain_root


def get_paths() -> BrainPaths:
    env = os.environ.get("WIKI_BRAIN")
    root = Path(env).resolve() if env else find_brain_root()
    if root is None or not (root / ".llmwiki").exists():
        raise BrainNotFoundError(
            "Brain não encontrado. Defina WIKI_BRAIN ou rode a API dentro de um brain."
        )
    return BrainPaths(root=root)


def get_config() -> WorkspaceConfig:
    return load_config(get_paths())


def open_conn(paths: BrainPaths) -> sqlite3.Connection:
    from ...db.connection import get_connection

    return get_connection(paths.db_path)
