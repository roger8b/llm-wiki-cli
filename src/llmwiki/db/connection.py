"""Opening and initializing the SQLite connection."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def _load_schema() -> str:
    return resources.files("llmwiki.db").joinpath("schema.sql").read_text(encoding="utf-8")


def get_connection(db_path: Path, apply_schema: bool = True) -> sqlite3.Connection:
    """Opens the connection, applies the schema (idempotently), and enables foreign keys.

    ``pages_fts`` (FTS5) is required; if the local SQLite does not support FTS5, the error
    is explicitly propagated.

    Set ``apply_schema=False`` on hot paths that open a fresh connection repeatedly (e.g.
    the job-worker poll loop). Re-running ``schema.sql`` re-issues the FTS5 virtual-table
    creation every call, which libsqlite3 logs as "API called with NULL prepared statement /
    misuse". The schema must already have been applied once for the connection to be usable.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not apply_schema:
        return conn
    try:
        conn.executescript(_load_schema())
    except sqlite3.OperationalError as exc:
        if "fts5" in str(exc).lower():
            raise RuntimeError(
                "Your SQLite does not support FTS5, which is required for search. "
                "Please install a Python version with SQLite+FTS5."
            ) from exc
        raise
    conn.commit()
    return conn
