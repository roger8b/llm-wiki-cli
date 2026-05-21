"""API FastAPI — casca fina sobre os services. Mesma lógica da CLI.

Inclui uma UI mínima de Review Changes em ``GET /`` (HTML embutido, sem build).
"""

from __future__ import annotations

from importlib import resources
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from ...core.errors import BrainNotFoundError, WikiError
from ...core.paths import BrainPaths
from ...db.repo import PageFtsRepo, PageRepo, SourceRepo
from ...services import (
    change_request_service,
    index_service,
    lint_service,
    query_service,
)
from .deps import get_config, get_paths, open_conn

app = FastAPI(title="llm-wiki API", version="2.0.0")


def _ctx() -> BrainPaths:
    try:
        return get_paths()
    except BrainNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------- sources
@app.get("/sources")
def list_sources() -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [s.model_dump(mode="json") for s in SourceRepo(conn).list()]
    finally:
        conn.close()


@app.post("/sources/ingest")
def ingest_source(path: str = Body(..., embed=True)) -> dict[str, Any]:
    from ...core.paths import resolve_input
    from ...services import ingest_service

    paths = _ctx()
    cfg = get_config()
    target = resolve_input(path, paths.root)
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"Arquivo não encontrado: {path}")
    conn = open_conn(paths)
    try:
        cr = ingest_service.ingest(target, paths, conn, cfg)
    except WikiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {"change_request_id": cr.id, "files_changed": cr.files_changed}


# ------------------------------------------------------------------ pages
@app.get("/wiki/pages")
def list_pages() -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [p.model_dump(mode="json") for p in PageRepo(conn).list()]
    finally:
        conn.close()


@app.get("/wiki/pages/{page_path:path}")
def get_page(page_path: str) -> dict[str, Any]:
    paths = _ctx()
    target = paths.root / page_path
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    from ...core import frontmatter

    meta, body = frontmatter.parse(target.read_text(encoding="utf-8"))
    return {"path": page_path, "frontmatter": meta, "body": body}


# ------------------------------------------------------------------ query
@app.post("/query")
def query(
    question: str = Body(..., embed=True),
    save_as_page: bool = Body(False, embed=True),
) -> dict[str, Any]:
    paths = _ctx()
    cfg = get_config()
    conn = open_conn(paths)
    try:
        result, cr = query_service.ask(question, paths, conn, cfg, save=save_as_page)
    finally:
        conn.close()
    out = result.model_dump(mode="json")
    out["change_request_id"] = cr.id if cr else None
    return out


# ------------------------------------------------------------------- lint
@app.post("/lint")
def lint(semantic: bool = Body(False, embed=True)) -> dict[str, Any]:
    paths = _ctx()
    if semantic:
        findings = lint_service.lint_all(paths, get_config(), semantic=True)
    else:
        findings = lint_service.lint_structural(paths)
    return {"findings": [f.model_dump(mode="json") for f in findings]}


# -------------------------------------------------------- change requests
@app.get("/change-requests")
def list_crs(status: str | None = Query(None)) -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [cr.model_dump(mode="json") for cr in change_request_service.list_crs(conn, status)]
    finally:
        conn.close()


@app.get("/change-requests/{cr_id}")
def get_cr(cr_id: str) -> dict[str, Any]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = change_request_service.get(cr_id, conn)
    finally:
        conn.close()
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request não encontrado.")
    return cr.model_dump(mode="json")


@app.post("/change-requests/{cr_id}/apply")
def apply_cr(cr_id: str, commit: bool = Body(False, embed=True)) -> dict[str, Any]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = change_request_service.apply(cr_id, paths, conn, git_commit=commit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {"id": cr.id, "status": cr.status}


@app.post("/change-requests/{cr_id}/reject")
def reject_cr(cr_id: str) -> dict[str, Any]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        change_request_service.reject(cr_id, conn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {"id": cr_id, "status": "rejected"}


# ---------------------------------------------------------- search / graph
@app.get("/search")
def search(q: str = Query(...)) -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        results = PageFtsRepo(conn).search(q)
    finally:
        conn.close()
    return [{"path": p, "title": t, "rank": r} for p, t, r in results]


@app.get("/graph")
def graph() -> dict[str, Any]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        from ...db.repo import LinkRepo

        index_service.reindex(paths, conn)
        pages = PageRepo(conn).list()
        links = LinkRepo(conn).all()
    finally:
        conn.close()
    nodes = [{"id": p.path, "title": p.title, "type": p.type.value} for p in pages]
    edges = [{"from": f, "to": t} for f, t, _ in links]
    return {"nodes": nodes, "edges": edges}


# -------------------------------------------------------------- review UI
@app.get("/", response_class=HTMLResponse)
def ui() -> str:
    return resources.files("llmwiki.interfaces.api").joinpath("review.html").read_text(
        encoding="utf-8"
    )
