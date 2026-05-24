"""Provider configuration endpoints (Ollama, Anthropic, OpenAI, Google)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Response

from ..deps import get_config

router = APIRouter()

_REMOTE_PROVIDERS = ("anthropic", "openai", "google")


def _provider_status() -> dict[str, Any]:
    """Per-provider config — never exposes API keys."""
    from ....core.secrets import has_api_key

    cfg = get_config()
    out: dict[str, Any] = {}
    for prov in _REMOTE_PROVIDERS:
        pc = cfg.providers.get(prov)
        out[prov] = {
            "base_url": pc.base_url if pc else None,
            "model": pc.model if pc else None,
            "has_key": has_api_key(prov),
        }
    return out


@router.get("/ollama")
def providers_ollama() -> dict[str, Any]:
    """Get Ollama status (running, models installed)."""
    from .. import setup as setup_mod

    return setup_mod.ollama_status()


@router.get("")
def providers_list() -> dict[str, Any]:
    """List all provider configurations."""
    return _provider_status()


@router.patch("/{provider}")
def providers_update(
    provider: str,
    base_url: str | None = Body(None, embed=True),
    model: str | None = Body(None, embed=True),
    api_key: str | None = Body(None, embed=True),
) -> dict[str, Any]:
    """Update a provider's configuration."""
    from ....core.config import update_config
    from ....core.secrets import set_api_key

    if provider not in _REMOTE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    if api_key:
        try:
            set_api_key(provider, api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    settings: dict[str, Any] = {}
    if base_url is not None:
        settings["base_url"] = base_url or None
    if model is not None:
        settings["model"] = model or None
    if settings:
        update_config({"providers": {provider: settings}})
    return _provider_status()[provider]


@router.delete("/{provider}/key")
def providers_delete_key(provider: str) -> dict[str, Any]:
    """Delete a provider's API key."""
    from ....core.secrets import delete_api_key

    if provider not in _REMOTE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    delete_api_key(provider)
    return _provider_status()[provider]


@router.post("/ollama/pull")
def providers_ollama_pull(model: str = Body(..., embed=True)) -> Response:
    """Proxy `ollama pull` and stream progress as SSE."""
    import json as _json
    import urllib.request

    from .setup import OLLAMA_URL

    def _events() -> Any:
        body = _json.dumps({"name": model, "stream": True}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if line:
                        yield f"data: {line}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        yield "data: {\"done\": true}\n\n"

    return Response(_events(), media_type="text/event-stream")