"""Search and graph endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..deps import get_paths, open_conn

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def search(q: str = Query(...)) -> list[dict[str, Any]]:
    """Full-text search across wiki pages."""
    from ....db.repo import PageFtsRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        results = PageFtsRepo(conn).search_snippets(q)
    finally:
        conn.close()
    # ``snippet`` is additive — existing clients that read path/title/rank are
    # unaffected (#171).
    return [
        {"path": p, "title": t, "rank": r, "snippet": s} for p, t, r, s in results
    ]


@router.get("/graph")
def graph() -> dict[str, Any]:
    """Get the wiki graph (nodes + edges)."""
    from ....db.repo import LinkRepo, PageRepo
    from ....services import index_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        index_service.reindex(paths, conn)
        pages = PageRepo(conn).list()
        links = LinkRepo(conn).all()
    finally:
        conn.close()
    nodes = [{"id": p.path, "title": p.title, "type": p.type.value} for p in pages]
    edges = [{"from": f, "to": t} for f, t, _ in links]
    return {"nodes": nodes, "edges": edges}