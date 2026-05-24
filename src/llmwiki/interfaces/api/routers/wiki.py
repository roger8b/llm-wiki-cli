"""Wiki pages, lint, and maintenance endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..deps import get_paths, open_conn

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pages")
def list_pages() -> list[dict[str, Any]]:
    """List all wiki pages."""
    from ....db.repo import PageRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [p.model_dump(mode="json") for p in PageRepo(conn).list()]
    finally:
        conn.close()


@router.get("/pages/{page_path:path}")
def get_page(page_path: str) -> dict[str, Any]:
    """Get a wiki page with parsed frontmatter."""
    from ....core import frontmatter
    from ....core.errors import PathOutsideBrainError
    from ....core.paths import resolve_input

    paths = _ctx()
    try:
        target = resolve_input(page_path, paths.root)
    except PathOutsideBrainError as exc:
        raise HTTPException(status_code=404, detail="Page not found.") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Page not found.")
    meta, body = frontmatter.parse(target.read_text(encoding="utf-8"))
    return {"path": page_path, "frontmatter": meta, "body": body}


@router.get("/backlinks")
def backlinks(path: str) -> dict[str, Any]:
    """Pages that link to ``path`` — the deletion impact preview."""
    from ....services import page_delete_service

    paths = _ctx()
    return {"path": path, "backlinks": page_delete_service.find_backlinks(path, paths)}


@router.post("/delete")
def delete_page(
    path: str = Body(..., embed=True),
    unlink_backlinks: bool = Body(False, embed=True),
) -> dict[str, Any]:
    """Propose deleting a page as a change request (optionally unlinking backlinks)."""
    from ....services import page_delete_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = page_delete_service.delete_page(
            path, paths, conn, unlink_backlinks=unlink_backlinks
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Page not found.") from exc
    finally:
        conn.close()
    return {"change_request_id": cr.id, "files_changed": cr.files_changed}


@router.post("/lint")
def lint(semantic: bool = Body(False, embed=True)) -> dict[str, Any]:
    """Run lint checks on the wiki."""
    from ....db.repo import JobRepo

    import json

    paths = _ctx()
    if semantic:
        conn = open_conn(paths)
        try:
            job_repo = JobRepo(conn)
            job_id = job_repo.create("lint", json.dumps({"semantic": True}), status="queued")
        finally:
            conn.close()
        return {"job_id": job_id}
    else:
        from ....services import lint_service

        findings = lint_service.lint_structural(paths)
        return {"findings": [f.model_dump(mode="json") for f in findings]}


@router.post("/maintain")
def maintain(semantic: bool = Body(False, embed=True)) -> dict[str, Any]:
    """Run lint and propose fixes as a change request."""
    from ....db.repo import JobRepo

    import json

    paths = _ctx()
    conn = open_conn(paths)
    try:
        job_repo = JobRepo(conn)
        job_id = job_repo.create("maintain", json.dumps({"semantic": semantic}), status="queued")
    finally:
        conn.close()
    return {"job_id": job_id}