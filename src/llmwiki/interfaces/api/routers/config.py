"""Workspace configuration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..deps import get_config, get_paths

router = APIRouter()


def _config_payload() -> dict[str, Any]:
    cfg = get_config()
    return {
        "model": cfg.model,
        "fts_limit": cfg.fts_limit,
        "num_ctx": cfg.num_ctx,
        "temperature": cfg.temperature,
        "request_timeout": cfg.request_timeout,
        "onboarded": cfg.onboarded,
        # Exposed so the Settings UI can read/edit them (#237). All are already
        # persisted via update_config (_CONFIG_KEYS); this only adds them to GET.
        "agent_max_retries": cfg.agent_max_retries,
        "agent_fix_retries": cfg.agent_fix_retries,
        "embedding_model": cfg.embedding_model,
        "chunk_threshold_chars": cfg.chunk_threshold_chars,
        "chunk_size_chars": cfg.chunk_size_chars,
        "chunk_overlap_chars": cfg.chunk_overlap_chars,
        "ingest_scope_concepts_per_chunk": cfg.ingest_scope_concepts_per_chunk,
        "whisper_model": cfg.whisper_model,
        "whisper_language": cfg.whisper_language,
        # Ask path (#350, epic #348). Default stays "agent" — `rag`/`auto` are
        # opt-in: −64% tokens_in, but no citations and p50 unchanged (ADR 002).
        "ask_mode": cfg.ask_mode,
        "ask_rag_top_k": cfg.ask_rag_top_k,
        "ask_rag_max_context_chars": cfg.ask_rag_max_context_chars,
        # Ingestion core (#352, epic #348). Default stays "deepagents" —
        # "minimal" wins on long sources and loses on short ones (ADR 002).
        "agent_core": cfg.agent_core,
        "minimal_max_turns": cfg.minimal_max_turns,
        # Output cap (#351, epic #348). Default is no cap; the per-op map wins
        # over the global one, with "outline" inheriting "ingest" (ADR 002).
        "max_output_tokens": cfg.max_output_tokens,
        "max_output_tokens_by_op": cfg.max_output_tokens_by_op,
        # Multi-query expansion (#355, epic #348). Default 0 = byte-identical
        # search; N variants buy recall on vague queries with latency (ADR 002).
        "search_query_expansion": cfg.search_query_expansion,
    }


@router.get("")
def get_config_endpoint() -> dict[str, Any]:
    """Get current workspace configuration."""
    return _config_payload()


@router.patch("")
def patch_config_endpoint(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Update configuration (partial update)."""
    from pydantic import ValidationError

    from ....core.config import update_config

    try:
        update_config(patch)
    except ValidationError as exc:
        # A rejected value must not reach the file, or the next GET would blow
        # up loading it (#370).
        raise HTTPException(status_code=400, detail=exc.errors(include_url=False)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _config_payload()


@router.get("/desktop")
def get_desktop_config() -> dict[str, Any]:
    """Desktop-shell settings (read by the Tauri shell, #204)."""
    from ....core.desktop import read_desktop

    return read_desktop(get_paths())


@router.patch("/desktop")
def patch_desktop_config(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Update desktop-shell settings (partial)."""
    from ....core.desktop import update_desktop

    return update_desktop(get_paths(), patch)


@router.post("/test")
def config_test(model: str = Body(..., embed=True)) -> dict[str, Any]:
    """Test if a model is available."""
    from .. import setup as setup_mod

    return setup_mod.test_model(model)