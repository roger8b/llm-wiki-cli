"""API FastAPI — casca fina sobre os services. Mesma lógica da CLI.

Inclui uma UI mínima de Review Changes em ``GET /`` (HTML embutido, sem build).
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Body,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ...core.errors import BrainNotFoundError, WikiError
from ...core.paths import WIKI_HOME, BrainPaths
from ...db.repo import PageFtsRepo, PageRepo, SourceRepo
from ...services import (
    change_request_service,
    index_service,
    lint_service,
    query_service,
)
from .deps import get_config, get_paths, open_conn

app = FastAPI(title="llm-wiki API", version="2.0.0")

# CORS — allow the Vite dev server (localhost:5173) to call the API during
# development. In production the SPA is served from the same origin, so this
# is a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory holding the built SPA (populated by `npm run build` in ui/).
_DIST = Path(__file__).parent / "dist"

# All JSON endpoints live under /api so they never collide with client-side
# SPA routes (e.g. /sources, /graph are both API and UI paths).
api = APIRouter()


def _ctx() -> BrainPaths:
    try:
        return get_paths()
    except BrainNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _provider_error(exc: Exception) -> str:
    """Turn a raw LLM/provider exception into a readable, actionable message."""
    msg = str(exc)
    if "not found" in msg and "model" in msg:
        return (
            f"{msg}. Pull it (e.g. `ollama pull <model>`) or change the model "
            "in Settings."
        )
    if "Connection" in msg or "refused" in msg or "ConnectError" in msg:
        return (
            "Could not reach the model provider. Is Ollama running "
            "(or your API key set)? Original error: " + msg
        )
    return f"Model provider error: {msg}"


# ---------------------------------------------------------------- sources
@api.get("/sources")
def list_sources() -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [s.model_dump(mode="json") for s in SourceRepo(conn).list()]
    finally:
        conn.close()


@api.post("/sources/ingest")
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
    except Exception as exc:  # noqa: BLE001 — surface LLM/provider errors cleanly
        raise HTTPException(status_code=502, detail=_provider_error(exc)) from exc
    finally:
        conn.close()
    return {"change_request_id": cr.id, "files_changed": cr.files_changed}


def _register_temp_source(name: str, data: bytes) -> dict[str, Any]:
    """Write bytes to a temp file, register it as a source, return the source."""
    import tempfile

    from ...sources.manager import add_source

    paths = _ctx()
    safe = Path(name).name or "untitled.md"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_file = Path(tmp) / safe
        tmp_file.write_bytes(data)
        conn = open_conn(paths)
        try:
            result = add_source(tmp_file, paths, SourceRepo(conn))
        finally:
            conn.close()
    return result.source.model_dump(mode="json")


@api.post("/sources/upload")
async def upload_source(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    data = await file.read()
    return _register_temp_source(file.filename or "untitled", data)


@api.post("/sources/text")
def add_text_source(
    title: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
) -> dict[str, Any]:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "note"
    body = content if content.startswith("#") else f"# {title}\n\n{content}"
    return _register_temp_source(f"{slug}.md", body.encode("utf-8"))


# ------------------------------------------------------------------ pages
@api.get("/wiki/pages")
def list_pages() -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [p.model_dump(mode="json") for p in PageRepo(conn).list()]
    finally:
        conn.close()


@api.get("/wiki/pages/{page_path:path}")
def get_page(page_path: str) -> dict[str, Any]:
    paths = _ctx()
    target = paths.root / page_path
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    from ...core import frontmatter

    meta, body = frontmatter.parse(target.read_text(encoding="utf-8"))
    return {"path": page_path, "frontmatter": meta, "body": body}


# ------------------------------------------------------------------ query
@api.post("/query")
def query(
    question: str = Body(..., embed=True),
    save_as_page: bool = Body(False, embed=True),
) -> dict[str, Any]:
    paths = _ctx()
    cfg = get_config()
    conn = open_conn(paths)
    try:
        result, cr = query_service.ask(question, paths, conn, cfg, save=save_as_page)
    except WikiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface LLM/provider errors cleanly
        raise HTTPException(status_code=502, detail=_provider_error(exc)) from exc
    finally:
        conn.close()
    out = result.model_dump(mode="json")
    out["change_request_id"] = cr.id if cr else None
    return out


# ------------------------------------------------------------------- lint
@api.post("/lint")
def lint(semantic: bool = Body(False, embed=True)) -> dict[str, Any]:
    paths = _ctx()
    if semantic:
        findings = lint_service.lint_all(paths, get_config(), semantic=True)
    else:
        findings = lint_service.lint_structural(paths)
    return {"findings": [f.model_dump(mode="json") for f in findings]}


@api.post("/maintain")
def maintain(semantic: bool = Body(False, embed=True)) -> dict[str, Any]:
    """Run lint, then ask the LLM to propose fixes as a change request."""
    from ...services import maintenance_service

    paths = _ctx()
    cfg = get_config()
    if semantic:
        findings = lint_service.lint_all(paths, cfg, semantic=True)
    else:
        findings = lint_service.lint_structural(paths)
    if not findings:
        return {"change_request_id": None, "files_changed": 0, "findings": 0}
    conn = open_conn(paths)
    try:
        cr = maintenance_service.maintain(findings, paths, conn, cfg)
    except WikiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_provider_error(exc)) from exc
    finally:
        conn.close()
    return {
        "change_request_id": cr.id if cr else None,
        "files_changed": cr.files_changed if cr else 0,
        "findings": len(findings),
    }


# -------------------------------------------------------- change requests
@api.get("/change-requests")
def list_crs(status: str | None = Query(None)) -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [cr.model_dump(mode="json") for cr in change_request_service.list_crs(conn, status)]
    finally:
        conn.close()


@api.get("/change-requests/{cr_id}")
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


@api.post("/change-requests/{cr_id}/apply")
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


@api.post("/change-requests/{cr_id}/reject")
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
@api.get("/search")
def search(q: str = Query(...)) -> list[dict[str, Any]]:
    paths = _ctx()
    conn = open_conn(paths)
    try:
        results = PageFtsRepo(conn).search(q)
    finally:
        conn.close()
    return [{"path": p, "title": t, "rank": r} for p, t, r in results]


@api.get("/graph")
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


# ------------------------------------------------------------------ config
def _config_payload() -> dict[str, Any]:
    cfg = get_config()
    return {
        "model": cfg.model,
        "fts_limit": cfg.fts_limit,
        "num_ctx": cfg.num_ctx,
        "temperature": cfg.temperature,
        "request_timeout": cfg.request_timeout,
    }


@api.get("/config")
def get_config_endpoint() -> dict[str, Any]:
    return _config_payload()


@api.patch("/config")
def patch_config_endpoint(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Update only the keys present in the request body."""
    from ...core.config import update_config

    update_config(patch)
    return _config_payload()


# ------------------------------------------------------------------ brains
@api.get("/brains")
def list_brains() -> list[dict[str, Any]]:
    """List known brains (directories under ~/.wiki/brains/)."""
    brains_dir = WIKI_HOME / "brains"
    if not brains_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(brains_dir.iterdir()):
        if entry.is_dir():
            db = entry / "metadata.db"
            out.append(
                {
                    "name": entry.name,
                    "db_size": db.stat().st_size if db.exists() else 0,
                }
            )
    return out


# Mount every JSON endpoint under /api.
app.include_router(api, prefix="/api")


# -------------------------------------------------------------- SPA / static
if (_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_DIST / "assets"),
        name="assets",
    )


@app.get("/", response_class=HTMLResponse)
def ui_root() -> str:
    """Serve the built SPA, falling back to the legacy review.html."""
    index = _DIST / "index.html"
    if index.is_file():
        return index.read_text(encoding="utf-8")
    return resources.files("llmwiki.interfaces.api").joinpath("review.html").read_text(
        encoding="utf-8"
    )


@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_fallback(full_path: str) -> Any:
    """Client-side routing: any unmatched non-API path returns index.html.

    Registered last, so all explicit API routes above take precedence.
    """
    index = _DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")
