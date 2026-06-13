"""CLI `wiki apply --only` parsing & passthrough (#184)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from llmwiki.core.models import ChangeRequest
from llmwiki.interfaces.cli.main import app
from llmwiki.services import change_request_service

runner = CliRunner()


def _brain(tmp_path: Path, monkeypatch) -> None:
    runner.invoke(app, ["brain", "create", str(tmp_path / "b"), "--no-git"])


def test_only_passes_repeated_paths(tmp_path: Path, monkeypatch) -> None:
    _brain(tmp_path, monkeypatch)
    captured: dict = {}

    def fake_apply(cr_id, paths, conn, *, git_commit=False, paths_filter=None):
        captured["filter"] = paths_filter
        return ChangeRequest(
            id=cr_id,
            status="applied",
            diff_dir="x",
            created_at=datetime.now(UTC),
            applied_paths=["wiki/a.md"],
            rejected_paths=["wiki/b.md"],
        )

    monkeypatch.setattr(change_request_service, "apply", fake_apply)
    result = runner.invoke(
        app, ["apply", "CR-1", "--only", "wiki/a.md", "--only", "wiki/b.md"]
    )
    assert result.exit_code == 0
    assert captured["filter"] == ["wiki/a.md", "wiki/b.md"]
    assert "applied" in result.stdout and "rejected" in result.stdout


def test_no_only_passes_none(tmp_path: Path, monkeypatch) -> None:
    _brain(tmp_path, monkeypatch)
    captured: dict = {}

    def fake_apply(cr_id, paths, conn, *, git_commit=False, paths_filter=None):
        captured["filter"] = paths_filter
        return ChangeRequest(
            id=cr_id, status="applied", diff_dir="x", created_at=datetime.now(UTC),
            files_changed=2,
        )

    monkeypatch.setattr(change_request_service, "apply", fake_apply)
    result = runner.invoke(app, ["apply", "CR-1"])
    assert result.exit_code == 0
    assert captured["filter"] is None
