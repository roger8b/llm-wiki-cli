"""Tests for cooperative cancellation + retry (epic #121, #138/#139)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.errors import JobCancelledError
from llmwiki.llm_agents import factory
from llmwiki.llm_agents.middleware import CancellationMiddleware


class _Req:
    tools: list = []


class TestCancellationMiddleware:
    def test_raises_when_cancelled(self) -> None:
        mw = CancellationMiddleware(lambda: True)
        with pytest.raises(JobCancelledError):
            mw.wrap_model_call(_Req(), lambda r: "resp")

    def test_passes_through_when_not_cancelled(self) -> None:
        mw = CancellationMiddleware(lambda: False)
        assert mw.wrap_model_call(_Req(), lambda r: "resp") == "resp"


class _FlakyAgent:
    def __init__(self, fail_times: int, state: dict) -> None:
        self.calls = 0
        self._fail = fail_times
        self._state = state

    def invoke(self, _payload: dict) -> dict:
        self.calls += 1
        if self.calls <= self._fail:
            raise RuntimeError("transient network error")
        return self._state


class TestRetry:
    def _cfg(self, tmp_path: Path, retries: int) -> WorkspaceConfig:
        return WorkspaceConfig(brain_root=tmp_path, agent_max_retries=retries)

    def test_retries_then_succeeds(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(factory.time, "sleep", lambda *_: None)  # no real backoff
        agent = _FlakyAgent(fail_times=1, state={"messages": []})
        out = factory._invoke_with_retry(agent, "msg", self._cfg(tmp_path, retries=2))
        assert out == {"messages": []}
        assert agent.calls == 2

    def test_gives_up_after_attempts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(factory.time, "sleep", lambda *_: None)
        agent = _FlakyAgent(fail_times=5, state={"messages": []})
        with pytest.raises(RuntimeError, match="transient"):
            factory._invoke_with_retry(agent, "msg", self._cfg(tmp_path, retries=2))
        assert agent.calls == 2

    def test_cancellation_is_not_retried(self, tmp_path: Path) -> None:
        class _Cancelling:
            calls = 0

            def invoke(self, _p: dict) -> dict:
                self.__class__.calls += 1
                raise JobCancelledError("stop")

        agent = _Cancelling()
        with pytest.raises(JobCancelledError):
            factory._invoke_with_retry(agent, "msg", self._cfg(tmp_path, retries=3))
        assert _Cancelling.calls == 1
