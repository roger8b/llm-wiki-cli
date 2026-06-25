"""Index management endpoints (#305).

Two surfaces:
- ``POST /index/reindex`` — enqueue a background ``index`` job that rebuilds the
  wiki_pages / links / FTS / embeddings tables from the files on disk.
- ``GET /index/status`` — read-only drift detector: how many ``.md`` files are
  in the wiki dir vs how many rows are in ``wiki_pages``, plus embedding health
  and the last reindex timestamp.

The reindex itself runs as a ``index`` job so a large brain doesn't block the
HTTP request — same pattern as ``maintain`` and ``curate`` (ADR 001).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..deps import get_paths, open_conn

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _count_disk_files(wiki_dir: Path) -> int:
    """Count ``.md`` files under ``wiki/`` that the indexer would scan.

    Mirrors ``index_service._iter_wiki_files`` (excludes ``index.md`` /
    ``log.md``); kept inline so the status endpoint doesn't drag in the full
    indexer stack just to count files.
    """
    if not wiki_dir.is_dir():
        return 0
    return sum(
        1 for p in wiki_dir.rglob("*.md") if p.name not in ("index.md", "log.md")
    )


@router.post("/reindex")
def reindex_now(embeddings: bool = Body(True, embed=True)) -> dict[str, Any]:
    """Enqueue a reindex job. Returns ``{job_id}``.

    The worker calls ``index_service.reindex`` (which clears and rebuilds
    ``wiki_pages`` / ``links`` / ``pages_fts`` / ``page_tags`` and, when
    ``embeddings`` is True and an ``embedding_model`` is configured, refreshes
    ``page_embeddings``), then ``rebuild_index_md`` and persists
    ``last_reindex_at`` to the ``meta`` kv table.
    """
    from ....db.repo import JobRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        job_id = JobRepo(conn).create(
            "index", json.dumps({"embeddings": embeddings}), status="queued"
        )
    finally:
        conn.close()
    return {"job_id": job_id}


@router.get("/status")
def index_status() -> dict[str, Any]:
    """Report db×disk drift and embedding health — without reindexing.

    ``stale`` is True whenever ``db_pages != disk_files``; the front-end uses
    that to offer a "Reindex" button without polling the worker.
    """
    from ....core.config import load_config
    from ....db.repo import MetaRepo, PageRepo

    paths = _ctx()
    cfg = load_config(paths)
    conn = open_conn(paths)
    try:
        db_pages = len(PageRepo(conn).list())
        disk_files = _count_disk_files(paths.wiki)
        embeddings_enabled = bool(cfg.embedding_model)
        emb_count_row = conn.execute(
            "SELECT COUNT(DISTINCT path) AS n FROM page_embeddings"
        ).fetchone()
        embeddings_count = int(emb_count_row["n"]) if emb_count_row else 0
        last_reindex_at = MetaRepo(conn).get("last_reindex_at")
    finally:
        conn.close()

    drift = disk_files - db_pages
    return {
        "db_pages": db_pages,
        "disk_files": disk_files,
        "drift": drift,
        "stale": drift != 0,
        "embeddings": {
            "count": embeddings_count,
            "expected": db_pages,
            "enabled": embeddings_enabled,
        },
        "last_reindex_at": last_reindex_at,
    }
