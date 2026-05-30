"""Secure storage for provider API keys via the OS keychain (``keyring``).

On macOS this is the Keychain; Linux uses Secret Service; Windows uses the
Credential Manager. Keys are never written to ``config.yaml``.

Reading falls back to the provider's conventional env var so existing
env-based setups keep working.
"""

from __future__ import annotations

import os
from typing import Any

_SERVICE = "llm-wiki"

# Conventional env var per provider (read-only fallback).
_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def _keyring() -> Any:
    try:
        import keyring  # noqa: PLC0415

        return keyring
    except Exception:  # noqa: BLE001 — keyring or its backend unavailable
        return None


def set_api_key(provider: str, key: str) -> None:
    """Store ``key`` for ``provider`` in the OS keychain."""
    kr = _keyring()
    if kr is None:
        raise RuntimeError("No secure keychain backend available (keyring).")
    kr.set_password(_SERVICE, provider, key)


def get_api_key(provider: str) -> str | None:
    """Return the stored key, or the env-var fallback, or None."""
    kr = _keyring()
    if kr is not None:
        try:
            stored: str | None = kr.get_password(_SERVICE, provider)
            if stored:
                return stored
        except Exception:  # noqa: BLE001
            pass
    env = _ENV_VAR.get(provider)
    return os.environ.get(env) if env else None


def delete_api_key(provider: str) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(_SERVICE, provider)
    except Exception:  # noqa: BLE001 — not present
        pass


def has_api_key(provider: str) -> bool:
    return bool(get_api_key(provider))
