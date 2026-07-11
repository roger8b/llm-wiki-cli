"""Tests for multi-query expansion in hybrid search (#355, epic #348).

``hybrid_search`` accepts an injectable ``expander`` (query -> variant list);
all variant result lists fuse into one RRF. Default (no expander /
``search_query_expansion: 0``) is byte-identical. A failing expander degrades
silently to the original query (same pattern as the semantic-layer failure).
"""

from __future__ import annotations

import pytest

from llmwiki.db.connection import get_connection
from llmwiki.db.repo import PageFtsRepo, PageRepo
from llmwiki.search.service import hybrid_search


@pytest.fixture
def conn(tmp_path):
    conn = get_connection(tmp_path / "meta.db")
    yield conn
    conn.close()


def _add_page(conn, path: str, title: str, body: str) -> None:
    from datetime import UTC, datetime

    from llmwiki.core.models import Page, PageType

    PageRepo(conn).upsert(
        Page(
            path=path,
            title=title,
            type=PageType.concept,
            tags=[],
            confidence=None,
            last_updated_at=datetime.now(UTC),
            source_count=0,
        )
    )
    PageFtsRepo(conn).add(path, title, body, "[]")


@pytest.fixture
def seeded(conn):
    _add_page(conn, "wiki/concepts/ollama.md", "Ollama", "executar modelos localmente ollama")
    _add_page(conn, "wiki/concepts/rag.md", "RAG", "retrieval augmented generation")
    return conn


def test_no_expander_is_identical(seeded):
    base = hybrid_search(seeded, "rodar llm na minha máquina", limit=10)
    off = hybrid_search(seeded, "rodar llm na minha máquina", limit=10, expander=None)
    assert [h.path for h in base] == [h.path for h in off]


def test_variant_hit_enters_fused_ranking(seeded):
    """Query with no FTS match finds the page via an expander variant."""
    base = hybrid_search(seeded, "zzz-nada", limit=10)
    assert base == []

    def expander(q: str) -> list[str]:
        return [q, "executar modelos localmente"]

    hits = hybrid_search(seeded, "zzz-nada", limit=10, expander=expander)
    assert "wiki/concepts/ollama.md" in [h.path for h in hits]


def test_failing_expander_degrades_to_original(seeded):
    def expander(q: str) -> list[str]:
        raise RuntimeError("provider down")

    hits = hybrid_search(seeded, "ollama", limit=10, expander=expander)
    assert [h.path for h in hits] == ["wiki/concepts/ollama.md"]


def test_config_default_off(tmp_path):
    from llmwiki.core.config import WorkspaceConfig

    assert WorkspaceConfig(brain_root=tmp_path).search_query_expansion == 0


def test_build_expander_off_returns_none(tmp_path):
    from llmwiki.core.config import WorkspaceConfig
    from llmwiki.search.expansion import build_expander

    cfg = WorkspaceConfig(brain_root=tmp_path)
    assert build_expander(cfg) is None


def test_build_expander_caps_and_caches(tmp_path, monkeypatch):
    """Expander returns at most N variants (plus original) and memoizes."""
    from llmwiki.core.config import WorkspaceConfig
    from llmwiki.search import expansion

    calls = {"n": 0}

    def fake_generate(cfg, query):
        calls["n"] += 1
        return ["v1", "v2", "v3", "v4"]

    monkeypatch.setattr(expansion, "_generate_variants", fake_generate)
    expansion.reset_expansion_cache()
    cfg = WorkspaceConfig(brain_root=tmp_path, search_query_expansion=2)
    expander = expansion.build_expander(cfg)
    assert expander is not None
    out = expander("consulta vaga")
    assert out[0] == "consulta vaga"
    assert len(out) == 3  # original + 2 variants (cap)
    expander("consulta vaga")
    assert calls["n"] == 1  # cached
