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
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
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
        "onboarded": cfg.onboarded,
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


# ------------------------------------------------------- health / lifecycle
@api.get("/health")
def health() -> dict[str, Any]:
    """Lightweight readiness probe — no brain required.

    Used by the desktop (Tauri) shell to wait for the backend before showing
    the window.
    """
    try:
        root = str(get_paths().root)
    except HTTPException:
        root = None
    return {"status": "ok", "brain": root}


@api.post("/shutdown")
def shutdown() -> dict[str, Any]:
    """Gracefully stop the server (used by the desktop shell on app exit)."""
    import os
    import signal
    import threading

    def _stop() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    # defer so the HTTP response is flushed before the process exits
    threading.Timer(0.2, _stop).start()
    return {"status": "stopping"}


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


# --------------------------------------------------------- setup / onboarding
@api.get("/onboarding")
def onboarding_status() -> dict[str, Any]:
    """First-run status — drives whether the UI shows the onboarding flow."""
    from . import setup as setup_mod

    cfg = get_config()
    brains_dir = WIKI_HOME / "brains"
    n_brains = (
        len([d for d in brains_dir.iterdir() if d.is_dir()])
        if brains_dir.is_dir()
        else 0
    )
    return {
        "needs_onboarding": not cfg.onboarded,
        "model": cfg.model,
        "ollama": setup_mod.ollama_status(),
        "brains": n_brains,
    }


@api.get("/providers/ollama")
def providers_ollama() -> dict[str, Any]:
    from . import setup as setup_mod

    return setup_mod.ollama_status()


_REMOTE_PROVIDERS = ("anthropic", "openai", "google")


def _provider_status() -> dict[str, Any]:
    """Per-provider config (base_url, model, has_key) — never the key itself."""
    from ...core.secrets import has_api_key

    cfg = get_config()
    out: dict[str, Any] = {}
    for prov in _REMOTE_PROVIDERS:
        pc = cfg.providers.get(prov)
        out[prov] = {
            "base_url": pc.base_url if pc else None,
            "model": pc.model if pc else None,
            "has_key": has_api_key(prov),
        }
    return out


@api.get("/providers")
def providers_list() -> dict[str, Any]:
    return _provider_status()


@api.patch("/providers/{provider}")
def providers_update(
    provider: str,
    base_url: str | None = Body(None, embed=True),
    model: str | None = Body(None, embed=True),
    api_key: str | None = Body(None, embed=True),
) -> dict[str, Any]:
    from ...core.config import update_config
    from ...core.secrets import set_api_key

    if provider not in _REMOTE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    # api_key → keychain (never persisted to config.yaml)
    if api_key:
        try:
            set_api_key(provider, api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    # base_url / model → config (merged)
    settings: dict[str, Any] = {}
    if base_url is not None:
        settings["base_url"] = base_url or None
    if model is not None:
        settings["model"] = model or None
    if settings:
        update_config({"providers": {provider: settings}})
    return _provider_status()[provider]


@api.delete("/providers/{provider}/key")
def providers_delete_key(provider: str) -> dict[str, Any]:
    from ...core.secrets import delete_api_key

    if provider not in _REMOTE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    delete_api_key(provider)
    return _provider_status()[provider]


@api.post("/providers/ollama/pull")
def providers_ollama_pull(model: str = Body(..., embed=True)) -> StreamingResponse:
    """Proxy `ollama pull` and stream progress to the client as SSE."""
    import json as _json
    import urllib.request

    from .setup import OLLAMA_URL

    def _events() -> Any:
        body = _json.dumps({"name": model, "stream": True}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if line:
                        yield f"data: {line}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@api.post("/config/test")
def config_test(model: str = Body(..., embed=True)) -> dict[str, Any]:
    from . import setup as setup_mod

    return setup_mod.test_model(model)


# ----------------------------------------------------------------- cli tools
@api.get("/cli")
def cli_status() -> dict[str, Any]:
    from . import setup as setup_mod

    return setup_mod.cli_status()


@api.post("/cli/install")
def cli_install() -> dict[str, Any]:
    from . import setup as setup_mod

    return setup_mod.cli_install()


@api.delete("/cli")
def cli_uninstall() -> dict[str, Any]:
    from . import setup as setup_mod

    return setup_mod.cli_uninstall()


# Mount every JSON endpoint under /api (after all routes are attached).
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
