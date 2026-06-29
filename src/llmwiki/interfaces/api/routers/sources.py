"""Source management endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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


@router.delete("")
def delete_source(path: str = Body(..., embed=True)) -> dict[str, Any]:
    """Delete a non-ingested source by relative path (#310).

    Status codes:
      * 200 — file removed from ``raw/`` and the row dropped from the DB.
      * 400 — no path supplied, or the path escapes the brain.
      * 404 — no source row with that path (nothing to delete).
      * 409 — the source is already processed / error / processing. Deletion
        of an ingested source would orphan pages, CRs, links, and FTS rows —
        that cascade is a follow-up story, intentionally out of scope here.
    """
    from ....core.errors import (
        NotFoundError,
        PathOutsideBrainError,
        SourceAlreadyIngestedError,
    )
    from ....db.repo import SourceRepo
    from ....sources.manager import remove_source

    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    paths = _ctx()
    conn = open_conn(paths)
    try:
        repo = SourceRepo(conn)
        try:
            remove_source(path, paths, repo)
        except PathOutsideBrainError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SourceAlreadyIngestedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()
    return {"deleted": path}


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


def _url_timeout(paths: Any) -> int:
    from ....core.config import load_config

    return load_config(paths).request_timeout


def _truncate_preview(text: str, limit: int = 500) -> str:
    """Cut ``text`` at the last paragraph/line/space boundary before ``limit``.

    Avoids slicing mid-code-block (or mid-word) so the markdown preview the UI
    receives never starts a fence it does not close. Mirrors the fallback in
    ``manager.add_url`` for consistency.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("\n\n", "\n", " "):
        idx = cut.rfind(sep)
        if idx > limit // 2:  # ponytail: keep at least half the budget
            return cut[:idx].rstrip() + "…"
    return cut.rstrip() + "…"


@router.post("/url/preview")
def preview_url_source(url: str = Body(..., embed=True)) -> dict[str, Any]:
    """Fetch + extract a URL without saving — title and a short preview (#195)."""
    from ....core.errors import EmptyExtractionError, FetchError
    from ....sources.manager import fetch_and_extract_url

    paths = _ctx()
    try:
        extracted = fetch_and_extract_url(url, timeout=_url_timeout(paths))
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except EmptyExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "url": url,
        "title": extracted.title or urlparse(url).netloc or url,
        "author": extracted.author,
        "date": extracted.date,
        "preview": _truncate_preview(extracted.text),
    }


@router.post("/url")
def add_url_source(url: str = Body(..., embed=True)) -> dict[str, Any]:
    """Capture a web article by URL and register it as a source (#195)."""
    from ....core.errors import EmptyExtractionError, FetchError
    from ....db.repo import SourceRepo
    from ....sources.manager import add_url

    paths = _ctx()
    conn = open_conn(paths)
    try:
        result = add_url(url, paths, SourceRepo(conn), timeout=_url_timeout(paths))
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except EmptyExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        conn.close()
    return {
        **result.source.model_dump(mode="json"),
        "already_present": result.already_present,
    }