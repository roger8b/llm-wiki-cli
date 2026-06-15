"""Scheduled curator trigger (#41).

A tiny asyncio loop run from the backend lifespan: every tick it checks the
active brain's ``last_curation_at`` against ``curation_interval_hours`` and, when
due (and no curation job is already pending), enqueues a ``curate`` job. The
worker runs it. No OS cron — the desktop app (#204) keeps the backend alive.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from ..core.config import WorkspaceConfig, load_config
from ..core.paths import BrainPaths, load_active_brain
from ..db.connection import get_connection
from ..db.repo import JobRepo
from ..services import curator_service

logger = logging.getLogger("llmwiki.workers")

_TICK_SECONDS = 3600


def curation_due(last_iso: str | None, interval_hours: int, *, now: datetime) -> bool:
    """True when enough time has passed since the last curation (or never ran)."""
    if interval_hours <= 0:
        return False
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(last_iso)
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return now - last >= timedelta(hours=interval_hours)


def _curation_in_flight(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE type = 'curate' "
        "AND status IN ('queued', 'running') LIMIT 1"
    ).fetchone()
    return row is not None


def maybe_enqueue_curation(
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    now: datetime | None = None,
) -> int | None:
    """Enqueue a curate job if scheduling is on, it's due, and none is pending."""
    interval = cfg.curation_interval_hours
    if not interval:
        return None
    now = now or datetime.now(UTC)
    if not curation_due(curator_service.get_last_curation(conn), interval, now=now):
        return None
    if _curation_in_flight(conn):
        return None
    job_id = JobRepo(conn).create("curate", "{}", status="queued")
    logger.info("Scheduler enqueued curation job %s", job_id)
    return job_id


async def run_scheduler(stop_event: asyncio.Event, *, tick_seconds: int = _TICK_SECONDS) -> None:
    """Background loop; exits promptly when ``stop_event`` is set."""
    logger.info("Curation scheduler started.")
    while not stop_event.is_set():
        try:
            paths = load_active_brain()
            cfg = load_config(paths)
            if cfg.curation_interval_hours:
                conn = get_connection(paths.db_path, apply_schema=False)
                try:
                    maybe_enqueue_curation(paths, conn, cfg)
                finally:
                    conn.close()
        except Exception:
            logger.exception("Curation scheduler tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
        except TimeoutError:
            pass
