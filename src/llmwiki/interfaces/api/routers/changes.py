"""Change request endpoints."""

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


@router.get("")
def list_crs(status: str | None = None) -> list[dict[str, Any]]:
    """List change requests, optionally filtered by status."""
    from ....services import change_request_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [cr.model_dump(mode="json") for cr in change_request_service.list_crs(conn, status)]
    finally:
        conn.close()


@router.get("/{cr_id}")
def get_cr(cr_id: str) -> dict[str, Any]:
    """Get a specific change request."""
    from ....services import change_request_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = change_request_service.get(cr_id, conn)
    finally:
        conn.close()
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found.")
    return cr.model_dump(mode="json")


@router.post("/{cr_id}/apply")
def apply_cr(cr_id: str, commit: bool = Body(False, embed=True)) -> dict[str, Any]:
    """Apply a change request to the wiki."""
    from ....services import change_request_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = change_request_service.apply(cr_id, paths, conn, git_commit=commit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {"id": cr.id, "status": cr.status}


@router.post("/{cr_id}/reject")
def reject_cr(cr_id: str) -> dict[str, Any]:
    """Reject a change request."""
    from ....services import change_request_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        change_request_service.reject(cr_id, conn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {"id": cr_id, "status": "rejected"}