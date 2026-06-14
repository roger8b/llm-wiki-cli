"""Ask history + answer promotion endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..deps import get_paths, open_conn

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _row_to_item(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "citations": json.loads(row["citations"]) if row["citations"] else [],
        "change_request_id": row["change_request_id"],
        "created_at": row["created_at"],
        "conversation_id": row["conversation_id"],
    }


@router.get("/history")
def list_history(limit: int = 50) -> list[dict[str, Any]]:
    """Permanent, per-brain history of past questions and answers."""
    from ....db.repo import AskHistoryRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        return [_row_to_item(r) for r in AskHistoryRepo(conn).list(limit)]
    finally:
        conn.close()


@router.delete("/history/{history_id}")
def delete_history(history_id: int) -> dict[str, Any]:
    """Delete a single history entry."""
    from ....db.repo import AskHistoryRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        AskHistoryRepo(conn).delete(history_id)
    finally:
        conn.close()
    return {"status": "deleted", "id": history_id}


@router.delete("/history")
def clear_history() -> dict[str, Any]:
    """Clear the entire ask history for the active brain."""
    from ....db.repo import AskHistoryRepo

    paths = _ctx()
    conn = open_conn(paths)
    try:
        AskHistoryRepo(conn).clear()
    finally:
        conn.close()
    return {"status": "cleared"}


@router.post("/promote")
def promote(
    question: str = Body(..., embed=True),
    answer: str = Body(..., embed=True),
    title: str | None = Body(None, embed=True),
    history_id: int | None = Body(None, embed=True),
) -> dict[str, Any]:
    """Promote an already-generated answer into a wiki-page change request.

    Does not re-run the LLM — it wraps the existing answer in a synthesis page
    and proposes it as a change request.
    """
    from ....db.repo import AskHistoryRepo
    from ....services import query_service

    paths = _ctx()
    conn = open_conn(paths)
    try:
        cr = query_service.promote_answer(question, answer, paths, conn, title=title)
        if cr is None:
            raise HTTPException(status_code=409, detail="Page already exists (no changes).")
        if history_id is not None:
            AskHistoryRepo(conn).set_change_request(history_id, cr.id)
        return {"change_request_id": cr.id, "files_changed": cr.files_changed}
    finally:
        conn.close()
