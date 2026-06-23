"""Eliminate redundant per-tool-call work (#278).

Three independent wins, each measured here:
- wiki_stats is memoized by the DB file signature, so multiple ingestion passes
  scan the page table once (and the cache invalidates when the DB changes);
- the semantic embedder is built once per config and reused across tool calls
  instead of being reconstructed on every search;
- the static system prompt is marked cacheable only on compatible providers.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import SystemMessage

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents import tools
from llmwiki.llm_agents.factory import _cached_prompt, _supports_prompt_cache
from llmwiki.llm_agents.tools import wiki_stats
from llmwiki.search import embeddings
from llmwiki.services import index_service


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


def _add_page(brain: BrainPaths, rel: str, title: str) -> None:
    page = brain.wiki / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"---\ntitle: {title}\ntype: concept\n---\n# {title}\nbody\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    tools.reset_wiki_stats_cache()
    embeddings.reset_embedder_cache()


class TestWikiStatsCache:
    def test_repeated_calls_scan_page_table_once(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_page(brain, "concepts/rag.md", "RAG")
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)
        finally:
            conn.close()

        from llmwiki.db.repo import PageRepo

        calls = {"n": 0}
        real_list = PageRepo.list

        def counting_list(self):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return real_list(self)

        monkeypatch.setattr(PageRepo, "list", counting_list)

        first = wiki_stats(brain)
        second = wiki_stats(brain)  # served from cache — no second scan
        third = wiki_stats(brain)
        assert first == second == third
        assert "1 páginas" in first
        assert calls["n"] == 1

    def test_cache_invalidates_when_db_changes(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)  # empty index
        finally:
            conn.close()
        assert "vazia" in wiki_stats(brain)

        _add_page(brain, "concepts/rag.md", "RAG")
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn)  # DB changes -> signature changes
        finally:
            conn.close()
        # Fresh count, not the cached "vazia".
        assert "1 páginas" in wiki_stats(brain)


class TestEmbedderReuse:
    def test_embedder_built_once_per_config(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = WorkspaceConfig(brain_root=brain.root, embedding_model="ollama:nomic-embed-text")
        builds = {"n": 0}

        def fake_build(_cfg):  # type: ignore[no-untyped-def]
            builds["n"] += 1
            return object()  # stand-in embedder; identity is what we assert on

        monkeypatch.setattr(embeddings, "_build_embedder", fake_build)

        first = embeddings.build_embedder(cfg)
        second = embeddings.build_embedder(cfg)
        assert first is second  # same object reused
        assert builds["n"] == 1

        embeddings.reset_embedder_cache()
        third = embeddings.build_embedder(cfg)
        assert builds["n"] == 2  # rebuilt after reset
        assert third is not first


class TestPromptCacheFlag:
    def test_marked_cacheable_only_on_compatible_providers(self, brain: BrainPaths) -> None:
        anthropic_cfg = WorkspaceConfig(brain_root=brain.root, model="anthropic:MiniMax-M3")
        ollama_cfg = WorkspaceConfig(brain_root=brain.root, model="ollama:llama3.1")

        assert _supports_prompt_cache(anthropic_cfg) is True
        assert _supports_prompt_cache(ollama_cfg) is False

        cached = _cached_prompt("ingestion.md", anthropic_cfg)
        assert isinstance(cached, SystemMessage)
        block = cached.content[0]
        assert block["cache_control"] == {"type": "ephemeral"}
        assert block["text"]  # carries the real prompt text

        plain = _cached_prompt("ingestion.md", ollama_cfg)
        assert isinstance(plain, str)
        assert plain  # unchanged plain-string behaviour
