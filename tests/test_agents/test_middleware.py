"""Tests for ExcludeToolsMiddleware (epic #123, story #145)."""

from __future__ import annotations

from types import SimpleNamespace

from llmwiki.agents.middleware import EXCLUDED_TOOLS, ExcludeToolsMiddleware


class _Req:
    def __init__(self, tools: list) -> None:
        self.tools = tools

    def override(self, *, tools: list) -> _Req:
        return _Req(tools)


def _tool(name: str):
    return SimpleNamespace(name=name)


def test_execute_is_in_default_exclusion() -> None:
    assert "execute" in EXCLUDED_TOOLS


def test_filters_execute_before_model() -> None:
    mw = ExcludeToolsMiddleware()
    seen: dict[str, list[str]] = {}

    def handler(req: _Req) -> str:
        seen["tools"] = [t.name for t in req.tools]
        return "resp"

    req = _Req([_tool("read_file"), _tool("execute"), _tool("write_file")])
    out = mw.wrap_model_call(req, handler)

    assert out == "resp"
    assert "execute" not in seen["tools"]
    assert {"read_file", "write_file"} <= set(seen["tools"])


def test_dict_tools_supported() -> None:
    mw = ExcludeToolsMiddleware()
    seen: dict[str, list] = {}

    def handler(req: _Req) -> None:
        seen["tools"] = list(req.tools)

    req = _Req([{"name": "execute"}, {"name": "ls"}])
    mw.wrap_model_call(req, handler)
    assert seen["tools"] == [{"name": "ls"}]


def test_empty_exclusion_is_noop() -> None:
    mw = ExcludeToolsMiddleware(excluded=frozenset())
    req = _Req([_tool("execute")])
    captured = {}

    def handler(r: _Req) -> None:
        captured["n"] = len(r.tools)

    mw.wrap_model_call(req, handler)
    assert captured["n"] == 1
