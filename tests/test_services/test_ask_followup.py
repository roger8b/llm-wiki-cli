"""Ask follow-up conversations (#190): window building, repo, migration."""

from __future__ import annotations

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import AskHistoryRepo
from llmwiki.llm_agents.models import QueryResult
from llmwiki.services import query_service


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


def test_build_history_context_empty() -> None:
    assert query_service.build_history_context([]) == ""


def test_build_history_context_truncates() -> None:
    turns = [("o que é RAG?", "R" * 5000)]
    block = query_service.build_history_context(turns, max_chars=500)
    assert len(block) <= 500
    assert block.endswith("…")
    assert "P: o que é RAG?" in block


def test_history_folded_into_agent_message(brain: BrainPaths) -> None:
    seen: dict[str, str] = {}

    def runner(cfg, backend, *, question, save):
        seen["question"] = question
        return QueryResult(answer="trade-off: custo vs latência.", citations=[])

    conn = get_connection(brain.db_path)
    try:
        result, _ = query_service.ask(
            "quais os trade-offs?",
            brain,
            conn,
            _cfg(brain),
            save=False,
            runner=runner,
            history_turns=[("o que é RAG?", "RAG recupera trechos relevantes.")],
        )
    finally:
        conn.close()
    msg = seen["question"]
    assert "CONVERSA ANTERIOR" in msg
    assert "o que é RAG?" in msg
    assert "PERGUNTA ATUAL: quais os trade-offs?" in msg
    assert "RAG recupera trechos" in msg


def test_no_history_keeps_plain_question(brain: BrainPaths) -> None:
    seen: dict[str, str] = {}

    def runner(cfg, backend, *, question, save):
        seen["question"] = question
        return QueryResult(answer="x", citations=[])

    conn = get_connection(brain.db_path)
    try:
        query_service.ask(
            "o que é RAG?", brain, conn, _cfg(brain), save=False, runner=runner
        )
    finally:
        conn.close()
    assert seen["question"] == "o que é RAG?"
    assert "CONVERSA ANTERIOR" not in seen["question"]


def test_recent_turns_window_and_order(brain: BrainPaths) -> None:
    conn = get_connection(brain.db_path)
    try:
        repo = AskHistoryRepo(conn)
        for i in range(6):
            repo.insert(f"q{i}", f"a{i}", conversation_id="conv-1")
        repo.insert("other", "a", conversation_id="conv-2")
        turns = repo.recent_turns("conv-1", limit=4)
    finally:
        conn.close()
    # Last 4 of conv-1, oldest first; conv-2 excluded.
    assert turns == [("q2", "a2"), ("q3", "a3"), ("q4", "a4"), ("q5", "a5")]


def test_migration_adds_conversation_id(brain: BrainPaths) -> None:
    conn = get_connection(brain.db_path)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(ask_history)")}
    finally:
        conn.close()
    assert "conversation_id" in cols
