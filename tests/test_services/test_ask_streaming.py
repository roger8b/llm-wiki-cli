"""Ask token streaming wiring (#191): runner receives on_token, tokens flow."""

from __future__ import annotations

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.llm_agents.models import QueryResult
from llmwiki.llm_agents.streaming import TokenBuffer
from llmwiki.services import query_service


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


def test_ask_forwards_tokens_to_on_token(brain: BrainPaths) -> None:
    seen: list[str] = []

    # A streaming-capable fake runner: emits chunks through on_token, then
    # returns the final structured answer.
    def runner(cfg, backend, *, question, save, on_token=None):
        for chunk in ["Hel", "lo ", "world"]:
            if on_token:
                on_token(chunk)
        return QueryResult(answer="Hello world", citations=[])

    conn = get_connection(brain.db_path)
    try:
        result, _ = query_service.ask(
            "hi?", brain, conn, _cfg(brain), runner=runner, on_token=seen.append
        )
    finally:
        conn.close()
    assert "".join(seen) == "Hello world"
    assert result.answer == "Hello world"


def test_ask_without_on_token_works_for_simple_runner(brain: BrainPaths) -> None:
    # Runners that don't accept on_token must keep working (no kwarg passed).
    def runner(cfg, backend, *, question, save):
        return QueryResult(answer="ok", citations=[])

    conn = get_connection(brain.db_path)
    try:
        result, _ = query_service.ask("hi?", brain, conn, _cfg(brain), runner=runner)
    finally:
        conn.close()
    assert result.answer == "ok"


def test_stream_buffer_persists_to_job_row(brain: BrainPaths) -> None:
    # Simulate the worker's buffer flushing the streamed text to jobs.stream_text.
    conn = get_connection(brain.db_path)
    try:
        repo = JobRepo(conn)
        job_id = repo.create("ask", '{"question": "x"}')
        buf = TokenBuffer(lambda t: repo.set_stream(job_id, t), max_chars=5)
        for tok in ["aaa", "bbb", "ccc"]:
            buf.add(tok)
        buf.flush()
        row = repo.get(job_id)
        assert row is not None
        assert row["stream_text"] == "aaabbbccc"
    finally:
        conn.close()
