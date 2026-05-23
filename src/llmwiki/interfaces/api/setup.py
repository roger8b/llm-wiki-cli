"""First-run setup helpers: provider detection, model test, CLI installation.

Pure functions used by the onboarding/Settings API endpoints. No FastAPI here
so they stay easy to unit-test.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ... import __version__

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# Provider → env var that must be set for hosted models.
_PROVIDER_KEY = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


# ───────────────────────────────────────────────── Ollama
def ollama_status() -> dict[str, Any]:
    """Is Ollama running, and which models are installed locally?"""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"running": False, "models": []}
    models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    return {"running": True, "models": sorted(models)}


# ───────────────────────────────────────────────── model test
def test_model(model: str) -> dict[str, Any]:
    """Lightweight connectivity check for a ``provider:model`` string.

    Ollama: confirm the daemon is up and the model is pulled.
    Hosted: confirm the provider's API-key env var is present.
    A wrong key still surfaces cleanly on first real use (502 handler).
    """
    provider, _, name = model.partition(":")
    if provider == "ollama":
        status = ollama_status()
        if not status["running"]:
            return {"ok": False, "detail": "Ollama is not running. Start it and retry."}
        installed = {m.split(":")[0]: m for m in status["models"]}
        if name in status["models"] or name.split(":")[0] in installed:
            return {"ok": True, "detail": "Model available locally."}
        return {
            "ok": False,
            "detail": f"Model '{name}' not pulled. Run: ollama pull {name}",
        }
    key = _PROVIDER_KEY.get(provider)
    if key is None:
        return {"ok": False, "detail": f"Unknown provider '{provider}'."}
    if os.environ.get(key):
        return {"ok": True, "detail": f"{key} is set."}
    return {"ok": False, "detail": f"{key} is not set in the environment."}


# ───────────────────────────────────────────────── CLI install
def _cli_source() -> str:
    """Path to the binary/script that should back the `wiki` command.

    When bundled by PyInstaller (desktop app) ``sys.executable`` IS the wiki
    binary. Otherwise fall back to an installed `wiki` on PATH.
    """
    if getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("wiki") or sys.argv[0]


def _cli_target() -> Path:
    return Path.home() / ".local" / "bin" / "wiki"


def _on_path(directory: Path) -> bool:
    parts = os.environ.get("PATH", "").split(os.pathsep)
    return str(directory) in parts


def cli_status() -> dict[str, Any]:
    target = _cli_target()
    found = shutil.which("wiki")
    return {
        "installed": target.exists() or target.is_symlink(),
        "path": str(target),
        "found_on_path": found,
        "on_path": _on_path(target.parent),
        "version": __version__,
        "source": _cli_source(),
    }


def cli_install() -> dict[str, Any]:
    """Symlink the wiki binary into ~/.local/bin (no admin required)."""
    source = Path(_cli_source()).resolve()
    target = _cli_target()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    try:
        target.symlink_to(source)
    except OSError:
        # symlink not allowed → copy instead
        shutil.copy2(source, target)
        target.chmod(0o755)
    return cli_status()


def cli_uninstall() -> dict[str, Any]:
    target = _cli_target()
    if target.exists() or target.is_symlink():
        target.unlink()
    return cli_status()
