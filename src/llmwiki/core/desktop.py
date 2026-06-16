"""Desktop-shell settings stored in ``<brain>/.llmwiki/desktop.json`` (#204).

These are settings that only the Tauri desktop shell acts on (e.g. whether to
keep running in the background tray on window close). They live in a small JSON
file — not the workspace config DB — because the Rust shell reads the same file
directly without going through the API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .paths import BrainPaths

logger = logging.getLogger("llmwiki.core")

DESKTOP_NAME = "desktop.json"

# Defaults applied when a key is missing or the file does not exist.
# ``notify_granularity`` (#275): "terminal" notifies only on finish/error,
# "all" also pings when an ingestion starts. Read by the Rust tray.
_DEFAULTS: dict[str, Any] = {
    "run_in_background": True,
    "notify_on_jobs": True,
    "notify_granularity": "terminal",
}


def _path(paths: BrainPaths):
    return paths.dot / DESKTOP_NAME


def read_desktop(paths: BrainPaths) -> dict[str, Any]:
    """Return the desktop settings merged over defaults (never raises)."""
    out = dict(_DEFAULTS)
    try:
        data = json.loads(_path(paths).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    if isinstance(data, dict):
        for key in _DEFAULTS:
            if key in data and isinstance(data[key], type(_DEFAULTS[key])):
                out[key] = data[key]
    return out


def update_desktop(paths: BrainPaths, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge ``patch`` into the desktop settings and persist; return the result."""
    current = read_desktop(paths)
    for key, value in patch.items():
        if key in _DEFAULTS and isinstance(value, type(_DEFAULTS[key])):
            current[key] = value
    path = _path(paths)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current), encoding="utf-8")
    except OSError:
        logger.warning("Could not write desktop settings at %s", path)
    return current
