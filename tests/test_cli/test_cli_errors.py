"""Standardised exit codes and JSON error envelopes (#198)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from llmwiki.core.errors import (
    JobCancelledError,
    ProviderError,
    SourceAlreadyProcessedError,
)
from llmwiki.interfaces.cli import _errors
from llmwiki.interfaces.cli.main import app
from llmwiki.services import ingest_service, query_service

runner = CliRunner()


def _brain(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "b"
    runner.invoke(app, ["brain", "create", str(root), "--no-git"])
    monkeypatch.chdir(root)
    return root


# --- unit: classification table -------------------------------------------------

def test_classify_codes() -> None:
    assert _errors.classify(SourceAlreadyProcessedError("x")) == (4, "source_already_processed")
    assert _errors.classify(JobCancelledError("x")) == (130, "cancelled")
    assert _errors.classify(ProviderError("x")) == (5, "provider_error")
    assert _errors.classify(ValueError("x")) == (1, "error")


# --- integration via CliRunner --------------------------------------------------

def test_review_not_found_exits_3(tmp_path: Path, monkeypatch) -> None:
    _brain(tmp_path, monkeypatch)
    r = runner.invoke(app, ["review", "CR-NOPE"])
    assert r.exit_code == 3


def test_review_not_found_json_envelope(tmp_path: Path, monkeypatch) -> None:
    _brain(tmp_path, monkeypatch)
    r = runner.invoke(app, ["review", "CR-NOPE", "--json"])
    assert r.exit_code == 3
    assert r.stdout.strip() == ""  # stdout stays clean
    env = json.loads(r.stderr)
    assert env["error"]["code"] == "not_found"
    assert env["error"]["exit_code"] == 3


def test_ingest_missing_file_single_exits_3(tmp_path: Path, monkeypatch) -> None:
    _brain(tmp_path, monkeypatch)
    r = runner.invoke(app, ["ingest", "nope.md"])
    assert r.exit_code == 3


def test_ingest_already_processed_single_exits_4(tmp_path: Path, monkeypatch) -> None:
    root = _brain(tmp_path, monkeypatch)
    src = root / "raw" / "a.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# A\nbody\n", encoding="utf-8")

    def boom(*a, **k):
        raise SourceAlreadyProcessedError("content already ingested.")

    monkeypatch.setattr(ingest_service, "ingest", boom)
    r = runner.invoke(app, ["ingest", str(src), "--json"])
    assert r.exit_code == 4
    assert r.stdout.strip() == ""
    env = json.loads(r.stderr)
    assert env["error"]["code"] == "source_already_processed"
    assert "force" in env["error"]["message"].lower()


def test_provider_error_exits_5(tmp_path: Path, monkeypatch) -> None:
    _brain(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise ProviderError("No API key configured for provider 'anthropic'.")

    monkeypatch.setattr(query_service, "ask", boom)
    r = runner.invoke(app, ["ask", "hello?"])
    assert r.exit_code == 5
