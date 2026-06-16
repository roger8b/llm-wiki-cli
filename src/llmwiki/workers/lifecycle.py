"""Sidecar lifecycle: server lockfile + post-crash job recovery (#203).

The backend writes ``<brain>/.llmwiki/server.lock`` (``{pid, port}``) on startup
and removes it on a clean shutdown. The Tauri shell reads it to kill exactly the
right stray process (instead of a broad ``pkill -f``). On startup the backend
also marks any ``running`` jobs as ``interrupted`` — a freshly started backend
cannot have a job genuinely running, so a leftover ``running`` row means the
previous process crashed mid-job.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..core.paths import BrainPaths

logger = logging.getLogger("llmwiki.workers")

LOCK_NAME = "server.lock"


@dataclass
class ServerLock:
    pid: int
    port: int | None


def lock_path(paths: BrainPaths) -> Path:
    return paths.dot / LOCK_NAME


def write_lock(paths: BrainPaths, *, pid: int | None = None, port: int | None = None) -> None:
    """Write the server lockfile (best effort)."""
    pid = os.getpid() if pid is None else pid
    path = lock_path(paths)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"pid": pid, "port": port}), encoding="utf-8")
    except OSError:
        logger.warning("Could not write server lockfile at %s", path)


def read_lock(paths: BrainPaths) -> ServerLock | None:
    path = lock_path(paths)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "pid" not in data:
        return None
    try:
        pid = int(data["pid"])
    except (TypeError, ValueError):
        return None
    port = data.get("port")
    return ServerLock(pid=pid, port=int(port) if isinstance(port, int) else None)


def remove_lock(paths: BrainPaths) -> None:
    try:
        lock_path(paths).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Could not remove server lockfile at %s", lock_path(paths))


def pid_alive(pid: int) -> bool:
    """True if a process with ``pid`` exists (signal 0 probe)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    return True


def recover_interrupted_jobs(conn: sqlite3.Connection) -> int:
    """Mark leftover ``running`` jobs as ``interrupted``; return how many.

    Called at backend startup before the worker runs, so any ``running`` row is
    necessarily an orphan from a previous crashed process.
    """
    cur = conn.execute(
        "UPDATE jobs SET status = 'interrupted', "
        "error = COALESCE(error, 'interrupted: backend restarted') "
        "WHERE status = 'running'"
    )
    conn.commit()
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
