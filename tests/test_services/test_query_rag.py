"""Tests for the single-shot RAG ask path (#350, epic #348).

``ask_mode: "agent"`` (default) keeps the legacy agent path byte-identical;
``"rag"`` retrieves top-k pages in code and makes ONE structured LLM call
(no tools); ``"auto"`` tries RAG and falls back to the agent path at most
once (0 hits or invalid citations).
"""

from __future__ import annotations

import pytest

from llmwiki.core.config import load_config
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents.models import Citation, QueryResult, SuggestedPage
from llmwiki.services import index_service, query_service, scaffold_service


@pytest.fixture
def brain(tmp_path, monkeypatch):
    from llmwiki.core import paths as paths_module

    monkeypatch.setattr(paths_module, "WIKI_HOME", tmp_path / ".wiki")
    paths = scaffold_service.init_brain(tmp_path / "brain", git=False)
    page = paths.root / "wiki/concepts/rag.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: RAG\ntype: concept\ntags: [rag]\nsources: []\n"
        "updated_at: 2026-01-01\nconfidence: high\n---\n# RAG\n\n"
        "Retrieval-Augmented Generation combina retriever e gerador.\n",
        encoding="utf-8",
    )
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    index_service.reindex(paths, conn, cfg)
    yield paths, conn, cfg
    conn.close()


def _rag_result(page: str = "wiki/concepts/rag.md") -> QueryResult:
    return QueryResult(answer="RAG combina retriever e gerador.", citations=[Citation(page=page)])


# --- mode selection ----------------------------------------------------------


def test_default_mode_is_agent(brain):
    """Without new config, only the legacy agent runner runs (regression-safe)."""
    paths, conn, cfg = brain
    assert cfg.ask_mode == "agent"
    calls: list[str] = []

    def agent_runner(cfg_, backend, *, question, save, **extra):
        calls.append("agent")
        return _rag_result()

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        calls.append("rag")
        return _rag_result()

    result, cr = query_service.ask(
        "o que é RAG?", paths, conn, cfg, runner=agent_runner, rag_runner=rag_runner
    )
    assert calls == ["agent"]
    assert cr is None
    assert not result.citations[0].invalid


def test_rag_mode_single_shot_with_context(brain):
    """rag mode: retrieval in code, rag runner gets page content, agent never runs."""
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "rag"})
    calls: list[str] = []
    seen: dict = {}

    def agent_runner(cfg_, backend, *, question, save, **extra):
        calls.append("agent")
        return _rag_result()

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        calls.append("rag")
        seen["context"] = context
        seen["question"] = question
        return _rag_result()

    result, _ = query_service.ask(
        "o que é RAG?", paths, conn, cfg, runner=agent_runner, rag_runner=rag_runner
    )
    assert calls == ["rag"]
    assert "wiki/concepts/rag.md" in seen["context"]
    assert "Retrieval-Augmented Generation" in seen["context"]
    assert result.citations[0].invalid is False


def test_rag_mode_respects_top_k_and_char_cap(brain):
    paths, conn, cfg = brain
    # add more pages so top_k matters
    for i in range(5):
        p = paths.root / f"wiki/concepts/rag-variant-{i}.md"
        p.write_text(
            f"---\ntitle: RAG Variant {i}\ntype: concept\ntags: [rag]\nsources: []\n"
            f"updated_at: 2026-01-01\nconfidence: high\n---\n# RAG Variant {i}\n\n"
            + ("RAG retrieval variante detalhe. " * 200),
            encoding="utf-8",
        )
    index_service.reindex(paths, conn, cfg)
    cfg = cfg.model_copy(
        update={"ask_mode": "rag", "ask_rag_top_k": 2, "ask_rag_max_context_chars": 1500}
    )
    seen: dict = {}

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        seen["context"] = context
        return _rag_result()

    query_service.ask("RAG", paths, conn, cfg, rag_runner=rag_runner)
    ctx = seen["context"]
    assert len(ctx) <= 1500 + 200  # cap + small header slack
    assert ctx.count("PÁGINA:") <= 2  # top_k


def test_auto_falls_back_on_invalid_citation(brain):
    """auto: rag first; invalid citation triggers ONE agent fallback."""
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "auto"})
    calls: list[str] = []

    def agent_runner(cfg_, backend, *, question, save, **extra):
        calls.append("agent")
        return _rag_result()  # valid

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        calls.append("rag")
        return _rag_result(page="wiki/concepts/nao-existe.md")  # invalid

    result, _ = query_service.ask(
        "o que é RAG?", paths, conn, cfg, runner=agent_runner, rag_runner=rag_runner
    )
    assert calls == ["rag", "agent"]
    assert result.citations[0].page == "wiki/concepts/rag.md"
    assert result.citations[0].invalid is False


def test_auto_falls_back_on_zero_hits(brain, tmp_path, monkeypatch):
    """auto with an empty index: no candidates -> agent path, rag never called."""
    from llmwiki.core import paths as paths_module

    monkeypatch.setattr(paths_module, "WIKI_HOME", tmp_path / ".wiki2")
    paths = scaffold_service.init_brain(tmp_path / "brain2", git=False)
    cfg = load_config(paths).model_copy(update={"ask_mode": "auto"})
    conn = get_connection(paths.db_path)
    index_service.reindex(paths, conn, cfg)
    calls: list[str] = []

    def agent_runner(cfg_, backend, *, question, save, **extra):
        calls.append("agent")
        return QueryResult(answer="wiki vazia")

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        calls.append("rag")
        return _rag_result()

    query_service.ask("qualquer", paths, conn, cfg, runner=agent_runner, rag_runner=rag_runner)
    conn.close()
    assert calls == ["agent"]


def test_rag_mode_no_fallback_even_when_invalid(brain):
    """pure rag: invalid citations flagged, but NO agent fallback."""
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "rag"})
    calls: list[str] = []

    def agent_runner(cfg_, backend, *, question, save, **extra):
        calls.append("agent")
        return _rag_result()

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        calls.append("rag")
        return _rag_result(page="wiki/concepts/nao-existe.md")

    result, _ = query_service.ask(
        "o que é RAG?", paths, conn, cfg, runner=agent_runner, rag_runner=rag_runner
    )
    assert calls == ["rag"]
    assert result.citations[0].invalid is True


# --- invariants --------------------------------------------------------------


def test_rag_save_creates_cr(brain):
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "rag"})

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        assert save is True
        r = _rag_result()
        r.suggested_page = SuggestedPage(
            path="wiki/synthesis/resposta-rag.md",
            content="---\ntitle: Resposta RAG\ntype: synthesis\ntags: []\nsources: []\n"
            "updated_at: 2026-01-01\nconfidence: medium\n---\n# Resposta RAG\n\nok\n",
        )
        return r

    result, cr = query_service.ask(
        "o que é RAG?", paths, conn, cfg, save=True, rag_runner=rag_runner
    )
    assert cr is not None
    assert cr.files_changed == 1


def test_rag_history_context_prepended(brain):
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "rag"})
    seen: dict = {}

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        seen["question"] = question
        return _rag_result()

    query_service.ask(
        "e as limitações?",
        paths,
        conn,
        cfg,
        rag_runner=rag_runner,
        history_turns=[("o que é RAG?", "RAG combina retriever e gerador.")],
    )
    assert "CONVERSA ANTERIOR" in seen["question"]
    assert "e as limitações?" in seen["question"]


def test_unknown_mode_falls_back_to_agent(brain):
    """Config with a bogus mode degrades safely to the agent path."""
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "yolo"})
    calls: list[str] = []

    def agent_runner(cfg_, backend, *, question, save, **extra):
        calls.append("agent")
        return _rag_result()

    def rag_runner(cfg_, backend, *, question, context, save, **extra):
        calls.append("rag")
        return _rag_result()

    query_service.ask("q", paths, conn, cfg, runner=agent_runner, rag_runner=rag_runner)
    assert calls == ["agent"]


def test_auto_buffers_rag_tokens_until_validated(brain):
    """auto + streaming: discarded RAG tokens never reach the live sink."""
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "auto"})
    streamed: list[str] = []

    def agent_runner(cfg_, backend, *, question, save, on_token=None, **extra):
        if on_token is not None:
            on_token("AGENT-TOK")
        return _rag_result()

    def rag_runner(cfg_, backend, *, question, context, save, on_token=None, **extra):
        if on_token is not None:
            on_token("RAG-TOK")
        return _rag_result(page="wiki/concepts/nao-existe.md")  # discarded

    query_service.ask(
        "o que é RAG?",
        paths,
        conn,
        cfg,
        runner=agent_runner,
        rag_runner=rag_runner,
        on_token=streamed.append,
    )
    assert streamed == ["AGENT-TOK"]


def test_auto_flushes_rag_tokens_on_success(brain):
    paths, conn, cfg = brain
    cfg = cfg.model_copy(update={"ask_mode": "auto"})
    streamed: list[str] = []

    def rag_runner(cfg_, backend, *, question, context, save, on_token=None, **extra):
        if on_token is not None:
            on_token("RAG-TOK")
        return _rag_result()  # valid -> survives

    query_service.ask(
        "o que é RAG?", paths, conn, cfg, rag_runner=rag_runner, on_token=streamed.append
    )
    assert streamed == ["RAG-TOK"]
