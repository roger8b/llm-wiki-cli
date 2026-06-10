"""Tests for the agent factory internals (epic #122).

Covers the pure, LLM-free building blocks: model construction, structured-output
extraction, the text fallback, and the response-format strategy. The full
``run_*`` flows are exercised via injected runners in the service tests.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import FileChange
from llmwiki.llm_agents import factory
from llmwiki.llm_agents.models import IngestionResult, QueryResult


def _cfg(tmp_path: Path, model: str = "ollama:llama3.1") -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=tmp_path, model=model)


class TestIngestionMessage:
    def test_includes_today_and_wiki_state(self, tmp_path: Path) -> None:
        from llmwiki.core.misc import today

        cfg = _cfg(tmp_path)
        msg = factory._ingestion_message(
            cfg, source_path="raw/articles/x.md", source_text="hello"
        )
        assert f"DATA DE HOJE: {today()}" in msg
        assert "ESTADO DA WIKI:" in msg
        assert "FONTE: raw/articles/x.md" in msg
        assert "hello" in msg

    def test_empty_wiki_does_not_break(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        msg = factory._ingestion_message(cfg, source_path="raw/x.md", source_text="t")
        assert "wiki vazia" in msg


class TestResponseFormat:
    def test_returns_tool_strategy(self) -> None:
        from langchain.agents.structured_output import ToolStrategy

        fmt = factory._response_format(IngestionResult)
        assert isinstance(fmt, ToolStrategy)


class TestStructured:
    def test_returns_schema_instance_as_is(self) -> None:
        want = IngestionResult(summary="ok", new_pages=["wiki/a.md"])
        got = factory._structured({"structured_response": want}, IngestionResult)
        assert got is want

    def test_validates_dict(self) -> None:
        state = {"structured_response": {"summary": "x", "new_pages": ["wiki/a.md"]}}
        got = factory._structured(state, IngestionResult)
        assert isinstance(got, IngestionResult)
        assert got.summary == "x"

    def test_falls_back_to_last_message_text(self) -> None:
        state = {
            "messages": [
                SimpleNamespace(content="early"),
                SimpleNamespace(content="final answer text"),
            ]
        }
        got = factory._structured(state, QueryResult)
        assert isinstance(got, QueryResult)
        assert got.answer == "final answer text"


class TestFallback:
    def test_fills_summary_field(self) -> None:
        out = factory._fallback(IngestionResult, "some summary")
        assert out.summary == "some summary"

    def test_fills_answer_full_not_truncated(self) -> None:
        text = "x" * 5000
        out = factory._fallback(QueryResult, text)
        assert out.answer == text  # answer never truncated

    def test_empty_text_uses_placeholder(self) -> None:
        out = factory._fallback(IngestionResult, "")
        assert out.summary  # non-empty placeholder

    def test_raises_when_schema_cannot_be_built(self) -> None:
        # FileChange has required fields not covered by the fallback (path/op/diff).
        with pytest.raises(RuntimeError):
            factory._fallback(FileChange, "text")


class TestHadStructured:
    def test_true_for_instance_and_dict(self) -> None:
        inst = {"structured_response": IngestionResult(summary="s")}
        assert factory._had_structured(inst, IngestionResult)
        assert factory._had_structured({"structured_response": {"summary": "s"}}, IngestionResult)

    def test_false_when_absent(self) -> None:
        assert not factory._had_structured({"messages": []}, IngestionResult)


class TestBuildModel:
    def test_ollama_returns_chat_object_not_string(self, tmp_path: Path) -> None:
        model = factory._build_model(_cfg(tmp_path, "ollama:llama3.1"))
        assert not isinstance(model, str)
        assert getattr(model, "model", "").endswith("llama3.1")

    def test_remote_sentinel_is_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = object()
        monkeypatch.setattr(factory, "_build_remote", lambda *a, **k: sentinel)
        assert factory._build_model(_cfg(tmp_path, "anthropic:claude")) is sentinel

    def test_remote_none_falls_back_to_model_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory, "_build_remote", lambda *a, **k: None)
        assert factory._build_model(_cfg(tmp_path, "openai:gpt-4o")) == "openai:gpt-4o"

    def test_ollama_does_not_read_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lazy key lookup (#147): the local Ollama path must not touch the keychain."""
        import llmwiki.core.secrets as secrets

        def _boom(provider: str) -> str:
            raise AssertionError(f"get_api_key should not be called for ollama (got {provider})")

        monkeypatch.setattr(secrets, "get_api_key", _boom)
        model = factory._build_model(_cfg(tmp_path, "ollama:llama3.1"))
        assert not isinstance(model, str)
