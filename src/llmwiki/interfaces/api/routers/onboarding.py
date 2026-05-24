"""Onboarding and first-run status endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .. import setup as setup_mod

router = APIRouter()


@router.get("")
def onboarding_status() -> dict[str, Any]:
    """First-run status — drives whether the UI shows the onboarding flow."""
    from ....core.brains import get_active_brain, list_brains
    from ....core.config import _DEFAULTS, _read_global_config

    data = _read_global_config()
    onboarded = bool(data.get("onboarded", False))
    model = data.get("model") or _DEFAULTS["model"]
    active = get_active_brain()
    return {
        "needs_onboarding": not onboarded,
        "model": model,
        "ollama": setup_mod.ollama_status(),
        "brains": len(list_brains()),
        "active_brain": active.to_dict() if active else None,
    }