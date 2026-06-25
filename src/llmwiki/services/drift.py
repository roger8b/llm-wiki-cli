"""Startup drift detection + optional auto-rebuild (#308).

The helper is the cheap half of the self-healing loop:

1. Compare ``count(.md em paths.wiki)`` vs ``count(wiki_pages)`` (two SQL
   COUNTs and a single rglob — never the full reindex).
2. If drift != 0 and ``cfg.index_autorebuild_on_drift``: enqueue an ``index``
   job — same INSERT the ``POST /api/index/reindex`` endpoint uses; the heavy
   rebuild runs in the worker, never in the lifespan.
3. Either way: record ``index_drift_stale``, ``index_drift_disk`` and
   ``index_drift_db`` in the ``meta`` kv so the UI / CLI can show "stale,
   click to reindex" without re-querying the file system.
4. Always log a single line with disk/db/job numbers so on-call sees the
   drift without hitting the status endpoint.

The cost is bounded by the two COUNTs and an rglob — for a 1k-page brain it
runs in <100ms on a developer laptop, well under the AC5 boot-budget.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from ..core.config import WorkspaceConfig
from ..core.paths import BrainPaths
from ..db.repo import JobRepo, MetaRepo

logger = logging.getLogger("llmwiki.services.drift")

# Kept in sync with index_service._SPECIAL so the disk count matches what a
# real reindex would see (index.md / log.md are special, not content pages).
_DISK_EXCLUDE = frozenset({"index.md", "log.md"})

# meta kv keys (UI/CLI can read these without going through the status router)
META_STALE = "index_drift_stale"
META_DISK = "index_drift_disk"
META_DB = "index_drift_db"


def _count_disk_files(wiki_dir: Path) -> int:
    if not wiki_dir.is_dir():
        return 0
    return sum(
        1 for p in wiki_dir.rglob("*.md") if p.name not in _DISK_EXCLUDE
    )


def detect_and_handle_drift(
    paths: BrainPaths, conn: sqlite3.Connection, cfg: WorkspaceConfig
) -> int:
    """Check db×disk drift and act on it. Returns ``drift`` (disk − db).

    Side effects when drift != 0:
    - ``meta`` kv: ``index_drift_stale=true``, ``index_drift_disk=N``,
      ``index_drift_db=M`` (always — so the UI can render the badge even
      while the auto-rebuild runs).
    - If ``cfg.index_autorebuild_on_drift``: an ``index`` job is enqueued
      and the job id is logged.
    """
    db_pages = int(conn.execute("SELECT COUNT(*) AS n FROM wiki_pages").fetchone()["n"])
    disk_files = _count_disk_files(paths.wiki)
    drift = disk_files - db_pages

    if drift == 0:
        # Clear stale flag so a freshly-synced brain stops showing the badge.
        meta = MetaRepo(conn)
        meta.set(META_STALE, "false")
        meta.set(META_DISK, str(disk_files))
        meta.set(META_DB, str(db_pages))
        logger.info("index drift=0 disk=%d db=%d", disk_files, db_pages)
        return drift

    meta = MetaRepo(conn)
    meta.set(META_STALE, "true")
    meta.set(META_DISK, str(disk_files))
    meta.set(META_DB, str(db_pages))

    if cfg.index_autorebuild_on_drift:
        job_id = JobRepo(conn).create(
            "index", json.dumps({"embeddings": True}), status="queued"
        )
        logger.warning(
            "index drift detected: disk=%d db=%d → enqueued reindex job #%d",
            disk_files,
            db_pages,
            job_id,
        )
    else:
        logger.warning(
            "index drift detected: disk=%d db=%d (auto-rebuild disabled; "
            "stale state persisted for UI/CLI)",
            disk_files,
            db_pages,
        )
    return drift