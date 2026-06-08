"""Opening and initializing the SQLite connection."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from importlib import resources
from pathlib import Path

# How long a writer waits for the WAL write lock before SQLite raises
# "database is locked". 15s comfortably absorbs another process's short
# write bursts (e.g. the desktop JobWorker committing while the CLI ingests).
BUSY_TIMEOUT_MS = 15000

# Some SQLITE_BUSY cases (lock upgrades, snapshot conflicts, checkpoint
# contention) are returned *without* honouring busy_timeout, so a writer can
# fail instantly even with a generous timeout. retry_on_locked() covers those.
LOCK_RETRY_ATTEMPTS = 6
LOCK_RETRY_BASE_DELAY = 0.05


def _load_schema() -> str:
    return resources.files("llmwiki.db").joinpath("schema.sql").read_text(encoding="utf-8")


def retry_on_locked[T](
    fn: Callable[[], T],
    *,
    attempts: int = LOCK_RETRY_ATTEMPTS,
    base_delay: float = LOCK_RETRY_BASE_DELAY,
) -> T:
    """Run ``fn`` (a write + commit), retrying on "database is locked".

    Covers the SQLITE_BUSY variants that bypass ``busy_timeout``. ``fn`` must be
    safe to re-run: SQLite takes the write lock on the first DML statement, so a
    locked failure means nothing was written and re-executing is idempotent.
    Backs off exponentially; re-raises the last error if all attempts fail or the
    error is not a lock error.
    """
    for attempt in range(attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2**attempt))
    raise AssertionError("unreachable")  # pragma: no cover


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
    # WAL lets the background job worker and API requests read/write concurrently
    # without the "database is locked" errors plain rollback-journal mode causes;
    # busy_timeout makes a writer wait for the lock instead of failing instantly.
    # journal_mode=WAL persists on the file; busy_timeout is per-connection.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = NORMAL")
    # Keep WAL autocheckpoint at its default (1000 pages) but set it explicitly:
    # the PASSIVE checkpoint it triggers never blocks other writers, unlike a
    # manual TRUNCATE checkpoint, so it won't add lock contention.
    conn.execute("PRAGMA wal_autocheckpoint = 1000")
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
