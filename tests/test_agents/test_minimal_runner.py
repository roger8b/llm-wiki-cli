"""Tests for the MinimalRunner core-swap experiment (#352, epic #348).

A thin native tool-calling loop over the LangChain chat model — no DeepAgents.
Invariants under test: staging writes via the backend, structured output via
the final tool, cooperative cancellation, turn limit, telemetry
(``ExecutionMeta``) and the ``agent_core`` config switch (default
``"deepagents"`` = byte-identical behaviour).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.errors import JobCancelledError
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.minimal import run_ingestion_minimal
from llmwiki.llm_agents.models import IngestionResult


class FakeModel:
    """Scripted chat model: returns the queued AIMessages, one per invoke."""

    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = list(replies)
        self.invokes = 0

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        return self

    def invoke(self, messages, **kwargs):
        self.invokes += 1
        if not self.replies:
            return AIMessage(content="")
        return self.replies.pop(0)


def _ai(tool_calls=None, content="", usage=(100, 20)):
    msg = AIMessage(content=content, tool_calls=tool_calls or [])
    msg.usage_metadata = {
        "input_tokens": usage[0],
        "output_tokens": usage[1],
        "total_tokens": sum(usage),
    }
    return msg


PAGE = (
    "---\ntitle: RAG\ntype: concept\ntags: [rag]\nsources: []\n"
    "updated_at: 2026-01-01\nconfidence: high\n---\n# RAG\n\ncorpo\n"
)


def _cfg(tmp_path: Path, **overrides) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=tmp_path, **overrides)


def test_happy_path_write_then_submit(tmp_path):
    backend = ChangeRequestBackend(tmp_path)
    model = FakeModel(
        [
            _ai(
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "wiki/concepts/rag.md", "content": PAGE},
                        "id": "c1",
                    }
                ]
            ),
            _ai(
                tool_calls=[
                    {
                        "name": "submit_result",
                        "args": {
                            "summary": "RAG ingerido",
                            "new_pages": ["wiki/concepts/rag.md"],
                            "affected_pages": [],
                        },
                        "id": "c2",
                    }
                ]
            ),
        ]
    )
    result = run_ingestion_minimal(
        _cfg(tmp_path),
        backend,
        source_path="raw/x.md",
        source_text="RAG é...",
        model=model,
    )
    assert isinstance(result, IngestionResult)
    assert result.summary == "RAG ingerido"
    assert backend.staging == {"wiki/concepts/rag.md": PAGE}
    meta = backend.execution_meta
    assert meta is not None
    assert meta.used_fallback is False
    assert meta.tool_calls == 2
    assert meta.tokens_in == 200 and meta.tokens_out == 40


def test_tool_error_is_fed_back_not_raised(tmp_path):
    """A rejected write (raw/) comes back as a tool message, loop continues."""
    backend = ChangeRequestBackend(tmp_path)
    model = FakeModel(
        [
            _ai(
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "raw/x.md", "content": PAGE},
                        "id": "c1",
                    }
                ]
            ),
            _ai(
                tool_calls=[
                    {
                        "name": "submit_result",
                        "args": {"summary": "ok", "new_pages": [], "affected_pages": []},
                        "id": "c2",
                    }
                ]
            ),
        ]
    )
    result = run_ingestion_minimal(
        _cfg(tmp_path), backend, source_path="raw/x.md", source_text="t", model=model
    )
    assert result.summary == "ok"
    assert backend.staging == {}  # rejected write never staged


def test_cancellation_between_turns(tmp_path):
    backend = ChangeRequestBackend(tmp_path)
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 1  # cancel before the 2nd model call

    backend.cancel_check = cancel
    model = FakeModel(
        [
            _ai(
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "wiki/concepts/a.md", "content": PAGE},
                        "id": "c1",
                    }
                ]
            ),
            _ai(content="never reached"),
        ]
    )
    with pytest.raises(JobCancelledError):
        run_ingestion_minimal(
            _cfg(tmp_path), backend, source_path="raw/x.md", source_text="t", model=model
        )
    assert model.invokes == 1


def test_text_json_coercion_291_parity(tmp_path):
    """Model that answers JSON as text (no submit tool) still yields a result."""
    backend = ChangeRequestBackend(tmp_path)
    model = FakeModel(
        [
            _ai(
                content='{"summary": "via texto", "new_pages": [], "affected_pages": []}',
            )
        ]
    )
    result = run_ingestion_minimal(
        _cfg(tmp_path), backend, source_path="raw/x.md", source_text="t", model=model
    )
    assert result.summary == "via texto"
    assert backend.execution_meta is not None
    assert backend.execution_meta.used_fallback is False  # coercion is not data loss


def test_turn_limit_degrades_to_fallback(tmp_path):
    backend = ChangeRequestBackend(tmp_path)
    looping = _ai(
        tool_calls=[
            {
                "name": "write_file",
                "args": {"file_path": "wiki/concepts/a.md", "content": PAGE},
                "id": "cx",
            }
        ]
    )
    model = FakeModel([looping] * 50)
    cfg = _cfg(tmp_path, minimal_max_turns=3)
    result = run_ingestion_minimal(
        cfg, backend, source_path="raw/x.md", source_text="t", model=model
    )
    assert model.invokes == 3
    assert isinstance(result, IngestionResult)
    assert backend.execution_meta is not None
    assert backend.execution_meta.used_fallback is True


def test_agent_core_config_routes_run_ingestion(tmp_path, monkeypatch):
    """cfg.agent_core='minimal' routes factory.run_ingestion to the minimal loop."""
    from llmwiki.llm_agents import factory, minimal

    sentinel = IngestionResult(summary="minimal-ran", new_pages=[], affected_pages=[])
    monkeypatch.setattr(minimal, "run_ingestion_minimal", lambda *a, **k: sentinel)
    cfg = _cfg(tmp_path, agent_core="minimal")
    backend = ChangeRequestBackend(tmp_path)
    out = factory.run_ingestion(cfg, backend, source_path="raw/x.md", source_text="t")
    assert out is sentinel


def test_agent_core_default_is_deepagents(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.agent_core == "deepagents"
