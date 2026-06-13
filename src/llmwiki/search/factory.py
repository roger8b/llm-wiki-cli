"""Wiring for the optional semantic search layer (#169).

``build_semantic_backend`` turns the workspace config into an
``(embedder, store)`` pair when semantic search is configured AND usable, or
``(None, None)`` otherwise. Consumers (hybrid_search, the search tool, CLI, API)
pass the pair through and degrade to pure FTS when it is ``None``.
"""

from __future__ import annotations

import logging
import sqlite3

from ..core.config import WorkspaceConfig
from .embeddings import build_embedder
from .service import EmbeddingProvider
from .vector_store import SqliteVecStore

logger = logging.getLogger("llmwiki.search.factory")


def build_semantic_backend(
    cfg: WorkspaceConfig, conn: sqlite3.Connection
) -> tuple[EmbeddingProvider | None, SqliteVecStore | None]:
    """Return ``(embedder, store)`` for semantic search, or ``(None, None)``.

    ``None`` when no ``embedding_model`` is set, the provider package is missing,
    or the sqlite-vec extension cannot be loaded.
    """
    embedder = build_embedder(cfg)
    if embedder is None:
        return None, None
    store = SqliteVecStore(conn)
    if not store.available:
        logger.warning(
            "embedding_model is set but sqlite-vec is unavailable; using FTS only "
            "(install the [semantic] extra)."
        )
        return None, None
    return embedder, store
