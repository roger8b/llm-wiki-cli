"""Workspace configuration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from ..deps import get_config

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
        "whisper_model": cfg.whisper_model,
        "whisper_language": cfg.whisper_language,
    }


@router.get("")
def get_config_endpoint() -> dict[str, Any]:
    """Get current workspace configuration."""
    return _config_payload()


@router.patch("")
def patch_config_endpoint(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Update configuration (partial update)."""
    from ....core.config import update_config

    update_config(patch)
    return _config_payload()


@router.post("/test")
def config_test(model: str = Body(..., embed=True)) -> dict[str, Any]:
    """Test if a model is available."""
    from .. import setup as setup_mod

    return setup_mod.test_model(model)