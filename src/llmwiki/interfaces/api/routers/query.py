"""Query endpoint."""

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


@router.post("")
def query(
    question: str = Body(..., embed=True),
    save_as_page: bool = Body(False, embed=True),
) -> dict[str, Any]:
    """Ask a question against the wiki (queued for background processing)."""
    import json

    from ....db.repo import JobRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        job_repo = JobRepo(conn)
        job_id = job_repo.create(
            "ask",
            json.dumps({"question": question, "save": save_as_page}),
            status="queued",
        )
    finally:
        conn.close()
    return {"job_id": job_id}