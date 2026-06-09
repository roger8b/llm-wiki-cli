"""Tests for the logging bootstrap (epic #119 / docs)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from llmwiki.core import logging as wiki_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    wiki_logging._CONFIGURED = False
    logging.getLogger("llmwiki").handlers.clear()


def test_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLMWIKI_LOG_LEVEL", "INFO")
    wiki_logging.configure_logging(force=True)
    assert logging.getLogger("llmwiki").level == logging.INFO


def test_default_level_is_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLMWIKI_LOG_LEVEL", raising=False)
    wiki_logging.configure_logging(force=True)
    assert logging.getLogger("llmwiki").level == logging.WARNING


def test_writes_to_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "wiki.log"
    monkeypatch.setenv("LLMWIKI_LOG_LEVEL", "INFO")
    monkeypatch.setenv("LLMWIKI_LOG_FILE", str(log_file))
    wiki_logging.configure_logging(force=True)
    logging.getLogger("llmwiki.llm_agents.factory").info("hello telemetry")
    assert log_file.exists()
    assert "hello telemetry" in log_file.read_text(encoding="utf-8")


def test_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLMWIKI_LOG_LEVEL", raising=False)
    wiki_logging.configure_logging(force=True)
    n = len(logging.getLogger("llmwiki").handlers)
    wiki_logging.configure_logging()  # not forced → no-op
    assert len(logging.getLogger("llmwiki").handlers) == n
