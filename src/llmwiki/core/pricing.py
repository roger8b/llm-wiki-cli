"""Static price table for estimating agent-run cost (#176).

Prices are USD per 1M tokens as ``(input, output)``. The table is intentionally
small and easy to edit; unknown models return ``None`` (cost not estimable)
rather than guessing. Local models (``ollama:``/``ollama/``) cost nothing.

Keys match the ``provider:model`` form used in ``WorkspaceConfig.model`` and the
telemetry ``execution.model`` field. Lookup is exact first, then by a relaxed
match on the bare model name so minor prefix differences still resolve.
"""

from __future__ import annotations

# USD per 1M tokens: (input, output)
PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "anthropic:claude-opus-4": (15.0, 75.0),
    "anthropic:claude-sonnet-4": (3.0, 15.0),
    "anthropic:claude-3-5-sonnet": (3.0, 15.0),
    "anthropic:claude-3-5-haiku": (0.80, 4.0),
    "anthropic:claude-3-haiku": (0.25, 1.25),
    # OpenAI
    "openai:gpt-4o": (2.50, 10.0),
    "openai:gpt-4o-mini": (0.15, 0.60),
    "openai:gpt-4.1": (2.0, 8.0),
    "openai:gpt-4.1-mini": (0.40, 1.60),
    # Google
    "google:gemini-1.5-pro": (1.25, 5.0),
    "google:gemini-1.5-flash": (0.075, 0.30),
    "google:gemini-2.0-flash": (0.10, 0.40),
}


def _normalize(model: str) -> str:
    return model.strip().lower()


def _lookup(model: str) -> tuple[float, float] | None:
    key = _normalize(model)
    if key in PRICES:
        return PRICES[key]
    # Relaxed: match on a known key being a prefix of the model (handles version
    # suffixes like ``anthropic:claude-sonnet-4-20250514``).
    for known, price in PRICES.items():
        if key.startswith(known):
            return price
    # Relaxed: match on the bare model name regardless of provider prefix.
    bare = key.split(":", 1)[-1]
    for known, price in PRICES.items():
        if known.split(":", 1)[-1] == bare:
            return price
    return None


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Estimate USD cost for a run. ``None`` when the model price is unknown."""
    key = _normalize(model)
    if key.startswith(("ollama:", "ollama/")):
        return 0.0
    price = _lookup(model)
    if price is None:
        return None
    return round(tokens_in / 1_000_000 * price[0] + tokens_out / 1_000_000 * price[1], 6)
