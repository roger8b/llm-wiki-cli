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


@router.get("/content")
def get_source_content(path: str) -> dict[str, Any]:
    """Return the textual content of a raw source for in-app reading.

    Resolves the path inside the brain (rejecting traversal), extracts text via
    the source extractors (md/txt; pdf/html fall back to a utf-8 read) and
    returns it alongside the classified ``type``.
    """
    from ....core.paths import resolve_input
    from ....sources.extractors import extract_text, source_type

    paths = _ctx()
    try:
        target = resolve_input(path, paths.root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Source not found: {path}")
    try:
        content = extract_text(target)
    except Exception as exc:  # noqa: BLE001 — binary/undecodable source
        content = f"[Could not render this source as text: {exc}]"
    return {"path": path, "type": source_type(target), "content": content}


@router.post("/ingest")
def ingest_source(
    path: str | None = Body(default=None, embed=True),
    paths_in: list[str] | None = Body(default=None, alias="paths", embed=True),  # noqa: B008
    force: bool = Body(default=False, embed=True),
) -> dict[str, Any]:
    """Queue one or more source files for background ingestion.

    Accepts either a single ``{"path": "..."}`` (kept for backwards
    compatibility) or a batch ``{"paths": ["a.md", "b.md"]}``. Each path is
    validated in isolation: invalid paths do not abort the batch. Returns the
    created ``job_ids`` plus per-path ``errors``. Responds 400 only when no job
    could be created.

    Pass ``force=true`` to skip the content-hash dedup that normally short-
    circuits re-ingestion of an already-processed source. The job payload
    carries the flag; the worker forwards it to the ingest service (#237
    follow-up: re-ingest from the UI).
    """
    import json

    from ....core.paths import resolve_input
    from ....db.repo import JobRepo

    targets = list(paths_in) if paths_in else ([path] if path else [])
    if not targets:
        raise HTTPException(status_code=400, detail="No path provided")

    paths = _ctx()
    job_ids: list[int] = []
    errors: list[dict[str, str]] = []
    conn = open_conn(paths)
    try:
        job_repo = JobRepo(conn)
        for p in targets:
            try:
                target = resolve_input(p, paths.root)
            except Exception as exc:  # path resolves outside brain, etc.
                errors.append({"path": p, "detail": str(exc)})
                continue
            if not target.is_file():
                errors.append({"path": p, "detail": f"File not found: {p}"})
                continue
            payload = json.dumps({"source": p, "force": bool(force)})
            job_id = job_repo.create("ingest", payload, status="queued")
            job_ids.append(job_id)
    finally:
        conn.close()

    if not job_ids:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Backwards-compatible single-path response.
    if path is not None and not paths_in:
        return {"job_id": job_ids[0]}
    return {"job_ids": job_ids, "errors": errors}


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