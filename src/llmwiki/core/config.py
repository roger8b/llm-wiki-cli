"""Global workspace configuration, stored at ``~/.wiki/config.yaml``.

The config file is shared across all brains on this machine. It is created
once (on the first ``wiki init``) and never overwritten by subsequent inits,
so the user's customisations are preserved.

Per-brain overrides are not currently supported; if needed in the future they
can be layered on top (brain-local config shadows global config).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from . import paths as _paths_module
from .paths import BrainPaths

# Fields that live in ~/.wiki/config.yaml (persisted + editable via the API).
# NOTE: API keys are NOT here — they live in the OS keychain (core.secrets).
_CONFIG_KEYS = (
    "model",
    "fts_limit",
    "num_ctx",
    "temperature",
    "request_timeout",
    "onboarded",
    "providers",
)

# Default config written on first init.
_DEFAULTS: dict[str, object] = {
    "model": "ollama:llama3.1",
    "fts_limit": 20,
    "num_ctx": 8192,
    "temperature": None,
    "request_timeout": 300,
    "onboarded": False,
    "providers": {},
}


class ProviderConfig(BaseModel):
    """Non-secret per-provider settings (the API key lives in the keychain)."""

    base_url: str | None = None
    model: str | None = None


class WorkspaceConfig(BaseModel):
    brain_root: Path
    model: str = "ollama:llama3.1"
    fts_limit: int = 20
    # LLM tuning (primarily for local Ollama models)
    num_ctx: int = 8192  # context window in tokens
    temperature: float | None = None  # None = provider default
    request_timeout: int = 300  # seconds
    # True once the user has completed the first-run onboarding flow.
    onboarded: bool = False
    # Per-provider settings keyed by provider name (openai|anthropic|google).
    providers: dict[str, ProviderConfig] = {}

    @property
    def paths(self) -> BrainPaths:
        return BrainPaths(root=self.brain_root)


def _config_file() -> Path:
    """Global config path: ~/.wiki/config.yaml

    Reading via module attribute so tests can monkeypatch
    ``llmwiki.core.paths.WIKI_HOME`` to redirect to a temp dir.
    """
    return _paths_module.WIKI_HOME / "config.yaml"


def load_config(paths: BrainPaths) -> WorkspaceConfig:
    """Load global config; fall back to defaults for missing fields."""
    cfg_path = _config_file()
    data: dict[str, object] = {}
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data["brain_root"] = paths.root
    return WorkspaceConfig.model_validate(data)


def write_default_config(paths: BrainPaths) -> None:  # noqa: ARG001
    """Write ~/.wiki/config.yaml with defaults if it doesn't exist yet.

    The ``paths`` argument is kept for API compatibility but is no longer used
    (config is now global, not per-brain).
    """
    cfg_path = _config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists():
        # Preserve the user's existing config — never overwrite.
        return
    cfg_path.write_text(
        yaml.safe_dump(_DEFAULTS, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def update_config(patch: dict[str, object]) -> None:
    """Merge ``patch`` into ~/.wiki/config.yaml, preserving other keys.

    Only known fields (``model``, ``fts_limit``) are persisted; unknown keys
    are ignored to keep the file clean.
    """
    cfg_path = _config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = dict(_DEFAULTS)
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = {**_DEFAULTS, **loaded}
    for key in _CONFIG_KEYS:
        if key not in patch:
            continue
        if key == "providers" and isinstance(patch[key], dict):
            # deep-merge per-provider settings instead of replacing the map
            current = dict(data.get("providers") or {})
            for prov, settings in patch[key].items():
                merged = dict(current.get(prov) or {})
                if isinstance(settings, dict):
                    merged.update(settings)
                current[prov] = merged
            data["providers"] = current
        else:
            data[key] = patch[key]  # allow None (e.g. temperature) explicitly
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
