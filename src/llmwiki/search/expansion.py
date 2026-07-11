"""Multi-query expansion for hybrid search (#355, epic #348).

The A/B on the golden set showed LLM-generated reformulations lifting vague
queries from 0.611 to 0.833 recall@5 (heuristic stopword variants: zero
effect). ``build_expander(cfg)`` returns a ``query -> [query, *variants]``
callable when ``search_query_expansion > 0``, else ``None`` (pure default —
byte-identical search).

The generator uses the "outline" model chain (cheap model when pinned, #293)
with ONE short completion per distinct query, memoized process-wide. Any
generator failure degrades silently to the original query — same policy as a
semantic-layer failure in ``hybrid_search``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..core.config import WorkspaceConfig

logger = logging.getLogger("llmwiki.search.expansion")

# query -> generated variants (without the original). Process-wide, like the
# prefetch/embedder caches (#278/#292); reset in tests.
_expansion_cache: dict[str, list[str]] = {}


def reset_expansion_cache() -> None:
    """Drop memoized expansions (used by tests for isolation)."""
    _expansion_cache.clear()


def _generate_variants(cfg: WorkspaceConfig, query: str) -> list[str]:
    """One short LLM completion with reformulations, one per line."""
    from ..llm_agents.factory import _build_model

    model = _build_model(cfg, "outline")
    out = model.invoke(
        [
            {
                "role": "user",
                "content": (
                    "Gere 3 reformulações curtas (sinônimos/termos técnicos) da "
                    "consulta de busca a seguir, uma por linha, sem numeração e "
                    f'sem explicação: "{query}"'
                ),
            }
        ]
    )
    content = out.content if isinstance(out.content, str) else str(out.content)
    return [line.strip().strip('"') for line in content.splitlines() if line.strip()]


def build_expander(cfg: WorkspaceConfig) -> Callable[[str], list[str]] | None:
    """Expander for ``cfg.search_query_expansion`` variants, or ``None`` (off)."""
    n = cfg.search_query_expansion
    if n <= 0:
        return None

    def expander(query: str) -> list[str]:
        variants = _expansion_cache.get(query)
        if variants is None:
            variants = _generate_variants(cfg, query)
            _expansion_cache[query] = variants
        return [query, *variants[:n]]

    return expander
