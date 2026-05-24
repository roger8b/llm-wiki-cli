"""Jobs management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..deps import get_paths, open_conn

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_jobs(limit: int = Query(50)) -> list[dict[str, Any]]:
    """List registered jobs."""
    from ....db.repo import JobRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        jobs = JobRepo(conn).list(limit=limit)
        return [dict(j) for j in jobs]
    finally:
        conn.close()


@router.get("/{job_id}")
def get_job(job_id: int) -> dict[str, Any]:
    """Get a specific job by ID."""
    from ....db.repo import JobRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        job = JobRepo(conn).get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return dict(job)
    finally:
        conn.close()