"""Context resolution (brain + config) for the API.

Active brain resolution is centralized in ``core.paths.load_active_brain``
(shared registry + self-heal), so API, CLI, and MCP see exactly the same selected brain.
"""

from __future__ import annotations

import sqlite3

from ...core.config import WorkspaceConfig, load_config
from ...core.paths import BrainPaths, load_active_brain


def get_paths() -> BrainPaths:
    """Active brain paths — delegates to the shared core resolver."""
    return load_active_brain()


def get_config() -> WorkspaceConfig:
    return load_config(get_paths())


def open_conn(paths: BrainPaths) -> sqlite3.Connection:
    from ...db.connection import get_connection

    return get_connection(paths.db_path)
