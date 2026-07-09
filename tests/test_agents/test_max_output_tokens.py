"""Tests for the per-operation output-token cap (#351, epic #348).

``max_output_tokens`` (global) + ``max_output_tokens_by_op`` (per operation)
plumb into the chat-model build. Default ``None`` = no cap, byte-identical
behaviour.
"""

from __future__ import annotations

from pathlib import Path

from llmwiki.core.config import WorkspaceConfig
from llmwiki.llm_agents.factory import resolve_max_output_tokens


def _cfg(**overrides) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=Path("/tmp/x"), **overrides)


def test_default_is_none():
    cfg = _cfg()
    assert cfg.max_output_tokens is None
    assert cfg.max_output_tokens_by_op == {}
    assert resolve_max_output_tokens(cfg, "ingest") is None
    assert resolve_max_output_tokens(cfg, None) is None


def test_global_cap_applies_to_all_operations():
    cfg = _cfg(max_output_tokens=2048)
    assert resolve_max_output_tokens(cfg, "ingest") == 2048
    assert resolve_max_output_tokens(cfg, "ask") == 2048
    assert resolve_max_output_tokens(cfg, None) == 2048


def test_per_op_override_wins_over_global():
    cfg = _cfg(max_output_tokens=2048, max_output_tokens_by_op={"ingest": 1024})
    assert resolve_max_output_tokens(cfg, "ingest") == 1024
    assert resolve_max_output_tokens(cfg, "ask") == 2048


def test_outline_falls_back_to_ingest_override():
    """outline inherits the ingest cap (same fallback chain as models, #293)."""
    cfg = _cfg(max_output_tokens_by_op={"ingest": 1024})
    assert resolve_max_output_tokens(cfg, "outline") == 1024


def test_zero_or_negative_disables_cap():
    """0 (explicit off) never reaches the provider as a real cap."""
    cfg = _cfg(max_output_tokens=0)
    assert resolve_max_output_tokens(cfg, "ingest") is None


def test_cap_reaches_ollama_model_kwargs():
    """End-to-end plumbing: the resolved cap lands on the chat model object."""
    from llmwiki.llm_agents.factory import _build_model

    cfg = _cfg(model="ollama:llama3.1", max_output_tokens_by_op={"ingest": 1234})
    model = _build_model(cfg, "ingest")
    assert getattr(model, "num_predict", None) == 1234
    # ask has no override and no global -> no cap
    model_ask = _build_model(cfg, "ask")
    assert getattr(model_ask, "num_predict", None) in (None, -1)
