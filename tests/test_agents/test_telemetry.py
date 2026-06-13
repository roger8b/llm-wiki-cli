"""Tests for agent execution telemetry (epic #119)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.llm_agents import factory
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.llm_agents.telemetry import ExecutionMeta, extract_meta


def _ai(content="", usage=None, tool_calls=None):
    return SimpleNamespace(content=content, usage_metadata=usage, tool_calls=tool_calls or [])


class TestExtractMeta:
    def test_sums_tokens_and_counts_tool_calls(self) -> None:
        state = {
            "messages": [
                _ai(usage={"input_tokens": 10, "output_tokens": 5}, tool_calls=[{"n": "s"}]),
                _ai(usage={"input_tokens": 7, "output_tokens": 3}, tool_calls=[{"a": 1}, {"b": 2}]),
            ]
        }
        meta = extract_meta(state, model="ollama:x", latency_ms=42, used_fallback=False)
        assert meta.tokens_in == 17
        assert meta.tokens_out == 8
        assert meta.tool_calls == 3
        assert meta.latency_ms == 42
        assert meta.model == "ollama:x"

    def test_missing_usage_is_zero(self) -> None:
        meta = extract_meta({"messages": [_ai()]}, model="m", latency_ms=0, used_fallback=False)
        assert meta.tokens_in == 0 and meta.tokens_out == 0 and meta.tool_calls == 0


class TestMerge:
    def test_empty_is_none(self) -> None:
        assert ExecutionMeta.merge([]) is None

    def test_sums_and_ors_fallback(self) -> None:
        a = ExecutionMeta("m", tokens_in=10, tokens_out=5, tool_calls=2, latency_ms=100)
        b = ExecutionMeta(
            "m", tokens_in=3, tokens_out=1, tool_calls=1, latency_ms=50, used_fallback=True
        )
        merged = ExecutionMeta.merge([a, b])
        assert merged is not None
        assert merged.model == "m"
        assert merged.tokens_in == 13
        assert merged.tokens_out == 6
        assert merged.tool_calls == 3
        assert merged.latency_ms == 150
        assert merged.used_fallback is True


class _FakeAgent:
    def __init__(self, state):
        self._state = state

    def invoke(self, _payload):
        return self._state


class TestInvoke:
    def test_captures_meta_on_backend(self, tmp_path) -> None:
        (tmp_path / "wiki").mkdir()
        backend = ChangeRequestBackend(tmp_path)
        state = {
            "structured_response": IngestionResult(summary="ok", new_pages=[]),
            "messages": [_ai(usage={"input_tokens": 4, "output_tokens": 2})],
        }
        cfg = WorkspaceConfig(brain_root=tmp_path)
        out = factory._invoke(_FakeAgent(state), "msg", IngestionResult, cfg, backend)
        assert out.summary == "ok"
        assert backend.execution_meta is not None
        assert backend.execution_meta.tokens_in == 4
        assert backend.execution_meta.used_fallback is False

    def test_logs_fallback_when_no_structured_response(
        self, tmp_path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "wiki").mkdir()
        backend = ChangeRequestBackend(tmp_path)
        state = {"messages": [_ai(content="plain text answer")]}  # no structured_response
        cfg = WorkspaceConfig(brain_root=tmp_path)
        with caplog.at_level(logging.WARNING, logger="llmwiki.llm_agents.factory"):
            factory._invoke(_FakeAgent(state), "msg", IngestionResult, cfg, backend)
        assert "fallback" in caplog.text
        assert backend.execution_meta is not None
        assert backend.execution_meta.used_fallback is True
