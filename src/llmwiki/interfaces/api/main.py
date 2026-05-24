"""FastAPI API — thin wrapper over services.

Router split:
- routers/brains.py   — brain registry CRUD
- routers/sources.py   — source management
- routers/wiki.py      — pages, lint, maintain
- routers/search.py    — FTS and graph
- routers/changes.py   — change requests
- routers/jobs.py      — background jobs
- routers/providers.py — provider config (Ollama, Anthropic, OpenAI, Google)
- routers/config.py   — workspace config
- routers/query.py    — wiki queries
- routers/onboarding.py — first-run flow
- routers/cli.py      — CLI install/uninstall
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from .deps import get_config, get_paths
from .routers import (
    brains_router,
    changes_router,
    cli_router,
    config_router,
    jobs_router,
    onboarding_router,
    providers_router,
    query_router,
    search_router,
    sources_router,
    wiki_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from ...workers import start_worker, stop_worker
    start_worker()
    yield
    stop_worker()


app = FastAPI(title="llm-wiki API", version="2.0.0", lifespan=lifespan)

# CORS — allow Vite dev server during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# All JSON endpoints live under /api to avoid collisions with SPA routes.
api = APIRouter()

# Mount domain routers under appropriate prefixes.
api.include_router(brains_router, prefix="/brains", tags=["brains"])
api.include_router(sources_router, prefix="/sources", tags=["sources"])
api.include_router(wiki_router, prefix="/wiki", tags=["wiki"])
api.include_router(search_router, prefix="/search", tags=["search"])
api.include_router(changes_router, prefix="/change-requests", tags=["changes"])
api.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api.include_router(providers_router, prefix="/providers", tags=["providers"])
api.include_router(cli_router, prefix="/cli", tags=["cli"])
api.include_router(query_router, prefix="/query", tags=["query"])
api.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])

# Config router is mounted without prefix (adds /config).
api.include_router(config_router, prefix="/config", tags=["config"])


# ─────────────────────────────────────── legacy top-level aliases
@api.post("/lint")
def lint(semantic: bool = False) -> dict[str, Any]:
    """Lint the wiki (structural by default)."""
    from .routers.wiki import _ctx, lint as _lint_impl
    paths = _ctx()
    return _lint_impl(semantic)


@api.get("/graph")
def graph() -> dict[str, Any]:
    """Wiki graph (nodes + edges)."""
    from .routers.search import _ctx, graph as _graph_impl
    paths = _ctx()
    return _graph_impl()


# ───────────────────────────── health / lifecycle
@api.get("/health")
def health() -> dict[str, Any]:
    """Lightweight readiness probe — no brain required."""
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

    threading.Timer(0.2, _stop).start()
    return {"status": "stopping"}


# Mount every JSON endpoint under /api (after all routes are attached).
app.include_router(api, prefix="/api")


# ───────────────────────────────────────────────────── SPA / static
_DIST = Path(__file__).parent / "dist"

if (_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")


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
    """Client-side routing: any unmatched non-API path returns index.html."""
    index = _DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")