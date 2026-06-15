"""Jobs management endpoints."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..deps import get_paths, open_conn

router = APIRouter()

# How often the SSE stream re-reads the job row, and when it gives up.
_POLL_SECONDS = 0.25
_STREAM_TIMEOUT_SECONDS = 600


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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


@router.get("/stats")
def jobs_stats(since: str | None = Query(None)) -> dict[str, Any]:
    """Per-model agent telemetry (tokens, latency, fallback, cost). Powers #151."""
    from ....services import stats_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        stats = stats_service.agent_stats(conn, paths, since=since)
        return {"stats": [s.model_dump(mode="json") for s in stats]}
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


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int) -> dict[str, Any]:
    """Request cooperative cancellation of a running job.

    Sets the ``cancel_requested`` flag; the worker's agent aborts at the next
    model-call boundary and the job ends in the ``cancelled`` state.
    """
    from ....db.repo import JobRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        repo = JobRepo(conn)
        job = repo.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job["status"] in ("done", "error", "cancelled"):
            return {"job_id": job_id, "status": job["status"], "cancel_requested": False}
        repo.request_cancel(job_id)
        return {"job_id": job_id, "status": job["status"], "cancel_requested": True}
    finally:
        conn.close()


def _job_event_stream(paths: Any, job_id: int) -> Iterator[str]:
    """Server-Sent Events for a job's lifecycle.

    Pushes ``status`` on every state change and a terminal ``result``/``error``
    the instant the worker finishes — replacing the client's 1s polling, so the
    answer (or job outcome) lands immediately. Runs in a worker thread (sync
    generator), so the ``time.sleep`` poll never blocks the event loop.
    """
    from ....db.repo import JobRepo

    conn = open_conn(paths)
    try:
        repo = JobRepo(conn)
        if repo.get(job_id) is None:
            yield _sse("error", {"detail": "Job not found."})
            return

        last_status: str | None = None
        last_progress: str | None = None
        last_stream_len = 0
        deadline = time.monotonic() + _STREAM_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            row = repo.get(job_id)
            if row is None:
                yield _sse("error", {"detail": "Job disappeared."})
                return
            status = row["status"]
            progress = row["progress"] if "progress" in row.keys() else None
            if progress != last_progress:
                last_progress = progress
                if progress:
                    yield _sse("progress", {"progress": progress})
            # Emit only the newly-streamed slice of the answer (#191).
            stream_text = row["stream_text"] if "stream_text" in row.keys() else None
            if stream_text and len(stream_text) > last_stream_len:
                yield _sse("token", {"text": stream_text[last_stream_len:]})
                last_stream_len = len(stream_text)
            if status != last_status:
                last_status = status
                yield _sse("status", {"status": status})
            if status == "done":
                yield _sse("result", {"result": row["result"]})
                yield _sse("end", {})
                return
            if status == "cancelled":
                yield _sse("cancelled", {"result": row["result"]})
                yield _sse("end", {})
                return
            if status == "error":
                yield _sse("error", {"detail": row["error"] or "Job failed."})
                return
            time.sleep(_POLL_SECONDS)
        yield _sse("error", {"detail": "Stream timed out."})
    finally:
        conn.close()


@router.get("/{job_id}/events")
def job_events(job_id: int) -> StreamingResponse:
    """Stream a job's progress + final result over SSE."""
    paths = _ctx()
    return StreamingResponse(
        _job_event_stream(paths, job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )