"""Tests for agent execution telemetry (epic #119)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.llm_agents import factory
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.llm_agents.telemetry import ExecutionMeta, extract_meta, tokens_by_source


def _ai(content="", usage=None, tool_calls=None):
    return SimpleNamespace(
        content=content, usage_metadata=usage, tool_calls=tool_calls or [], type="ai", name=None
    )


def _msg(type_, content="", name=None, usage=None):
    return SimpleNamespace(
        content=content, name=name, type=type_, usage_metadata=usage, tool_calls=[]
    )


class TestTokensBySource:
    def test_attributes_input_by_origin_with_resend(self) -> None:
        # tokenize = char count; invokes are AI messages with usage_metadata.
        # Each message is counted once per invoke that occurs AFTER it (re-send).
        messages = [
            _msg("system", "SYS"),  # 3 chars, 2 invokes after → 6
            _msg("human", "DOCDOC"),  # 6 chars, 2 invokes after → 12
            _ai(usage={"input_tokens": 9, "output_tokens": 1}),  # invoke 1 (idx2)
            _msg("tool", "HITS!", name="search_pages"),  # 5 chars, 1 invoke after → 5
            _ai(usage={"input_tokens": 14, "output_tokens": 1}),  # invoke 2 (idx4)
        ]
        res = tokens_by_source(messages, tokenize=len)
        assert res == {"system": 6, "document": 12, "search_tool": 5}

    def test_classifies_each_origin(self) -> None:
        messages = [
            _msg("system", "a"),
            _msg("human", "b"),
            _msg("tool", "c", name="search_by_type"),
            _msg("tool", "d", name="related_pages"),
            _msg("tool", "e", name="read_page"),
            _ai(content="f", usage={"input_tokens": 1, "output_tokens": 1}),
            _ai(usage={"input_tokens": 1, "output_tokens": 1}),  # trailing invoke
        ]
        res = tokens_by_source(messages, tokenize=lambda s: 1)
        # every non-AI msg has 2 invokes after it; the first AI (idx5) has 1 invoke after.
        assert res["system"] == 2
        assert res["document"] == 2
        assert res["search_tool"] == 2
        assert res["related_tool"] == 2
        assert res["other"] == 2
        assert res["assistant_history"] == 1

    def test_no_invokes_returns_empty(self) -> None:
        messages = [_msg("system", "x"), _msg("human", "y")]
        assert tokens_by_source(messages, tokenize=len) == {}

    def test_residual_reconciles_with_total_input(self) -> None:
        # System prompt isn't in the message list; the residual vs the provider's
        # tokens_in lands in system_framework so buckets sum to tokens_in exactly.
        messages = [
            _msg("tool", "HITS!", name="search_pages"),  # 5 chars, 1 invoke after → 5
            _ai(usage={"input_tokens": 100, "output_tokens": 1}),
        ]
        res = tokens_by_source(messages, total_input_tokens=100, tokenize=len)
        assert res["search_tool"] == 5
        assert res["system_framework"] == 95
        assert sum(res.values()) == 100

    def test_default_tokenizer_runs(self) -> None:
        messages = [
            _msg("system", "hello world"),
            _ai(usage={"input_tokens": 5, "output_tokens": 1}),
        ]
        res = tokens_by_source(messages)  # default tiktoken/fallback
        assert res.get("system", 0) > 0


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

    def test_includes_tokens_by_source(self) -> None:
        state = {
            "messages": [
                _msg("tool", "result text", name="search_pages"),
                _ai(usage={"input_tokens": 5, "output_tokens": 1}),
            ]
        }
        meta = extract_meta(state, model="m", latency_ms=0, used_fallback=False)
        assert meta.tokens_by_source.get("search_tool", 0) > 0


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

    def test_sums_tokens_by_source_per_bucket(self) -> None:
        a = ExecutionMeta("m", tokens_by_source={"system": 5, "search_tool": 2})
        b = ExecutionMeta("m", tokens_by_source={"system": 3, "document": 7})
        merged = ExecutionMeta.merge([a, b])
        assert merged is not None
        assert merged.tokens_by_source == {"system": 8, "search_tool": 2, "document": 7}


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
