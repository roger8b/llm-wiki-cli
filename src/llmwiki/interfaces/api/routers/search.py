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
def search(q: str = Query(...), limit: int = Query(20)) -> list[dict[str, Any]]:
    """Hybrid (keyword + semantic) content search across wiki pages (#188).

    Uses ``hybrid_search``: keyword snippets (#171) plus semantic results when an
    embedding model is configured (#169) — transparent to the caller. Each hit:
    ``{path, title, score, source, snippet}``.
    """
    from ....core.config import load_config
    from ....search.factory import build_semantic_backend
    from ....search.service import hybrid_search

    paths = _ctx()
    conn = open_conn(paths)
    try:
        embedder, store = build_semantic_backend(load_config(paths), conn)
        hits = hybrid_search(conn, q, limit=limit, embedder=embedder, store=store)
    finally:
        conn.close()
    return [
        {
            "path": h.path,
            "title": h.title,
            "score": h.score,
            "source": h.source,
            "snippet": h.snippet,
        }
        for h in hits
    ]


@router.get("/graph")
def graph() -> dict[str, Any]:
    """Get the wiki graph (nodes + edges)."""
    from ....core.config import load_config
    from ....db.repo import LinkRepo, PageRepo
    from ....services import index_service

    paths = _ctx()
    cfg = load_config(paths)
    conn = open_conn(paths)
    try:
        index_service.reindex(paths, conn, cfg)
        pages = PageRepo(conn).list()
        links = LinkRepo(conn).all()
    finally:
        conn.close()
    nodes = [
        {"id": p.path, "title": p.title, "type": p.type.value, "tags": p.tags}
        for p in pages
    ]
    edges = [{"from": f, "to": t} for f, t, _ in links]
    return {"nodes": nodes, "edges": edges}