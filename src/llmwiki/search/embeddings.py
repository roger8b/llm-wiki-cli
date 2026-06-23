"""Embedding providers for local semantic search (#169).

``build_embedder(cfg)`` returns an :class:`EmbeddingProvider` (the protocol in
``search.service``) for the configured ``embedding_model`` — ``"<provider>:<model>"``
— or ``None`` when semantic search is disabled or the provider package is
missing. Imports are lazy so the core works without the optional extras.
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.config import WorkspaceConfig

logger = logging.getLogger("llmwiki.search.embeddings")


class _LangchainEmbedder:
    """Adapter wrapping a LangChain embeddings object as an EmbeddingProvider."""

    def __init__(self, impl: Any) -> None:
        self._impl = impl

    def embed(self, text: str) -> list[float]:
        return [float(x) for x in self._impl.embed_query(text)]


def _build_ollama(name: str, cfg: WorkspaceConfig) -> Any | None:
    try:
        from langchain_ollama import OllamaEmbeddings  # noqa: PLC0415
    except ImportError:
        logger.warning("embedding_model is ollama:%s but langchain-ollama is not installed.", name)
        return None
    kwargs: dict[str, Any] = {"model": name}
    pcfg = cfg.providers.get("ollama")
    if pcfg and pcfg.base_url:
        kwargs["base_url"] = pcfg.base_url
    return OllamaEmbeddings(**kwargs)


def _build_openai(name: str, cfg: WorkspaceConfig) -> Any | None:
    try:
        from langchain_openai import OpenAIEmbeddings  # noqa: PLC0415
    except ImportError:
        logger.warning("embedding_model is openai:%s but langchain-openai is not installed.", name)
        return None
    from ..core.secrets import get_api_key  # noqa: PLC0415

    kwargs: dict[str, Any] = {"model": name}
    api_key = get_api_key("openai")
    if api_key:
        kwargs["api_key"] = api_key
    pcfg = cfg.providers.get("openai")
    if pcfg and pcfg.base_url:
        kwargs["base_url"] = pcfg.base_url
    return OpenAIEmbeddings(**kwargs)


def _embedder_key(cfg: WorkspaceConfig) -> tuple[str | None, str | None, str | None]:
    """Cache key capturing everything ``_build_embedder`` reads from ``cfg``."""
    ollama = cfg.providers.get("ollama")
    openai = cfg.providers.get("openai")
    return (
        cfg.embedding_model,
        ollama.base_url if ollama else None,
        openai.base_url if openai else None,
    )


# Process-wide cache so the embedder (model/client construction is the costly
# part) is built once and reused across every search_pages/related_pages tool
# call within an ingestion run instead of being rebuilt per call (#278). Keyed
# by the config fields the build reads, so a config change yields a fresh
# embedder. The per-connection vector store stays per-call (it wraps the
# short-lived SQLite connection each tool opens for thread safety).
_embedder_cache: dict[tuple[str | None, str | None, str | None], _LangchainEmbedder | None] = {}


def _build_embedder(cfg: WorkspaceConfig) -> _LangchainEmbedder | None:
    spec = cfg.embedding_model
    if not spec:
        return None
    provider, _, name = spec.partition(":")
    name = name or provider
    impl: Any | None
    if provider == "ollama":
        impl = _build_ollama(name, cfg)
    elif provider == "openai":
        impl = _build_openai(name, cfg)
    else:
        logger.warning("unsupported embedding provider %r (use ollama: or openai:).", provider)
        return None
    return _LangchainEmbedder(impl) if impl is not None else None


def build_embedder(cfg: WorkspaceConfig) -> _LangchainEmbedder | None:
    """Build (or reuse) an embedder from ``cfg.embedding_model`` or return ``None``.

    ``None`` means semantic search is off (no model configured) or the required
    provider package is unavailable — callers then use pure FTS. The result is
    memoized per config (#278) so repeated tool calls don't rebuild the client.
    """
    key = _embedder_key(cfg)
    if key in _embedder_cache:
        return _embedder_cache[key]
    embedder = _build_embedder(cfg)
    _embedder_cache[key] = embedder
    return embedder


def reset_embedder_cache() -> None:
    """Drop the memoized embedders (used by tests for isolation)."""
    _embedder_cache.clear()
