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


@router.patch("/{cr_id}/files")
def update_cr_file(
    cr_id: str,
    path: str = Body(..., embed=True),
    new_content: str = Body(..., embed=True),
) -> dict[str, Any]:
    """Edit one file's proposed content before the CR is applied (#183)."""
    from ....services import change_request_service as crs

    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = crs.update_change(cr_id, path, new_content, conn, paths)
    except (crs.CRNotFoundError, crs.CRPathNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except crs.CRInvalidPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (crs.CRStatusError, crs.CREmptyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()
    return cr.model_dump(mode="json")


@router.post("/{cr_id}/apply")
def apply_cr(
    cr_id: str,
    commit: bool = Body(False, embed=True),
    selected: list[str] | None = Body(None, embed=True, alias="paths"),  # noqa: B008
) -> dict[str, Any]:
    """Apply a change request to the wiki, optionally only ``paths`` (#184).

    With a ``paths`` subset, those files are applied and the rest rejected (the
    CR settles in one decision). Omitting ``paths`` applies everything.
    """
    from ....services import change_request_service as crs

    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = crs.apply(cr_id, paths, conn, git_commit=commit, paths_filter=selected)
    except crs.CRNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except crs.CRStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:  # path-not-in-CR, empty selection, invalid path
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {
        "id": cr.id,
        "status": cr.status,
        "applied_paths": cr.applied_paths,
        "rejected_paths": cr.rejected_paths,
    }


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