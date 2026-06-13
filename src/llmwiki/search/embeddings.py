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


def build_embedder(cfg: WorkspaceConfig) -> _LangchainEmbedder | None:
    """Build an embedder from ``cfg.embedding_model`` or return ``None``.

    ``None`` means semantic search is off (no model configured) or the required
    provider package is unavailable — callers then use pure FTS.
    """
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
