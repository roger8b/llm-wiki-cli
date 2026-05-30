"""Source management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from ..deps import get_paths, open_conn

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_sources() -> list[dict[str, Any]]:
    """List all registered sources."""
    from ....db.repo import SourceRepo
    from ....sources.manager import sync_sources

    paths = _ctx()
    conn = open_conn(paths)
    try:
        repo = SourceRepo(conn)
        sync_sources(paths, repo)
        return [s.model_dump(mode="json") for s in repo.list()]
    finally:
        conn.close()


@router.post("/ingest")
def ingest_source(path: str = Body(..., embed=True)) -> dict[str, Any]:
    """Ingest a source file (queued for background processing)."""
    import json

    from ....core.paths import resolve_input
    from ....db.repo import JobRepo

    paths = _ctx()
    target = resolve_input(path, paths.root)
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    conn = open_conn(paths)
    try:
        job_repo = JobRepo(conn)
        job_id = job_repo.create("ingest", json.dumps({"source": path}), status="queued")
    finally:
        conn.close()
    return {"job_id": job_id}


def _register_temp_source(name: str, data: bytes) -> dict[str, Any]:
    """Write bytes to a temp file, register it as a source, return the source."""
    import tempfile
    from pathlib import Path

    from ....db.repo import SourceRepo
    from ....sources.manager import add_source

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


@router.post("/upload")
async def upload_source(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    """Upload a file as a source."""
    data = await file.read()
    return _register_temp_source(file.filename or "untitled", data)


@router.post("/text")
def add_text_source(
    title: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
) -> dict[str, Any]:
    """Create a source from raw text."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "note"
    body = content if content.startswith("#") else f"# {title}\n\n{content}"
    return _register_temp_source(f"{slug}.md", body.encode("utf-8"))