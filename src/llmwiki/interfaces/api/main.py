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

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .deps import get_paths
from .routers import (
    ask_router,
    brains_router,
    changes_router,
    cli_router,
    config_router,
    jobs_router,
    onboarding_router,
    providers_router,
    query_router,
    search_router,
    skills_router,
    sources_router,
    wiki_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    from ...core.logging import configure_logging
    from ...workers import start_worker, stop_worker
    from ...workers.scheduler import run_scheduler

    configure_logging()
    _on_startup()
    start_worker()
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(run_scheduler(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        scheduler_task.cancel()
        stop_worker()
        _on_shutdown()


def _on_startup() -> None:
    """Recover orphan jobs from a prior crash and write the server lockfile (#203)."""
    from ...core.paths import load_active_brain
    from ...db.connection import get_connection
    from ...workers.lifecycle import recover_interrupted_jobs, write_lock

    try:
        paths = load_active_brain()
    except Exception:
        return
    try:
        conn = get_connection(paths.db_path)
        try:
            n = recover_interrupted_jobs(conn)
            if n:
                import logging

                logging.getLogger("llmwiki.workers").info(
                    "Recovered %d orphan running job(s) as interrupted.", n
                )
        finally:
            conn.close()
    except Exception:
        import logging

        logging.getLogger("llmwiki.workers").exception("Orphan-job recovery failed")
    port_env = os.getenv("LLMWIKI_SERVER_PORT")
    write_lock(paths, port=int(port_env) if port_env and port_env.isdigit() else None)


def _on_shutdown() -> None:
    from ...core.paths import load_active_brain
    from ...workers.lifecycle import remove_lock

    try:
        paths = load_active_brain()
    except Exception:
        return
    remove_lock(paths)


app = FastAPI(title="llm-wiki API", version="2.0.0", lifespan=lifespan)

# CORS — allow Vite dev server during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_token(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Gate /api/* on a per-session token when WIKI_API_TOKEN is set.

    The desktop shell generates a random token, passes it to this sidecar via the
    env var, and injects it into the WebView; the SPA echoes it as X-Wiki-Token.
    This blocks other local processes and browser-based (CSRF / DNS-rebinding)
    access to the brain. When the env var is unset (plain `wiki serve`, dev,
    tests) the API stays open — auth is opt-in.

    Exemptions: non-/api routes (the SPA + assets, loaded before JS runs),
    /api/health (the shell's readiness probe), /api/onboarding (first-run probe
    — exposes only the needs_onboarding boolean + brain count; gating it broke
    fresh installs when the token wasn't yet injected) and CORS preflight.
    """
    token = os.environ.get("WIKI_API_TOKEN")
    if token:
        path = request.url.path
        if (
            path.startswith("/api/")
            and path != "/api/health"
            and path != "/api/onboarding"
            and request.method != "OPTIONS"
            and request.headers.get("x-wiki-token") != token
        ):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


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
api.include_router(ask_router, prefix="/ask", tags=["ask"])
api.include_router(skills_router, prefix="/skills", tags=["skills"])
api.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])

# Config router is mounted without prefix (adds /config).
api.include_router(config_router, prefix="/config", tags=["config"])


# ─────────────────────────────────────── legacy top-level aliases
@api.post("/lint")
def lint(semantic: bool = False) -> dict[str, Any]:
    """Lint the wiki (structural by default)."""
    from .routers.wiki import lint as _lint_impl
    return _lint_impl(semantic)


@api.post("/maintain")
def maintain(semantic: bool = False) -> dict[str, Any]:
    """Lint and propose fixes as a change request (queues a maintain job)."""
    from .routers.wiki import maintain as _maintain_impl
    return _maintain_impl(semantic)


@api.get("/graph")
def graph() -> dict[str, Any]:
    """Wiki graph (nodes + edges)."""
    from .routers.search import graph as _graph_impl
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