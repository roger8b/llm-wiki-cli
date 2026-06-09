"""Regressão: conteúdo dinâmico com colchetes não pode quebrar o rich markup."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.interfaces.cli.main import app
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.services import change_request_service, scaffold_service

runner = CliRunner()


def _brain(tmp: Path) -> BrainPaths:
    return scaffold_service.init_brain(tmp / "b", git=False)


def test_review_with_brackets_in_summary(tmp_path: Path, monkeypatch) -> None:
    brain = _brain(tmp_path)
    backend = ChangeRequestBackend(brain.root)
    backend.write("wiki/concepts/x.md", "---\ntitle: X [v2]\ntype: concept\n---\n# X [v2]\n")
    conn = get_connection(brain.db_path)
    try:
        cr = change_request_service.create_from_changes(
            backend.collect_changes(),
            "Resumo com [colchetes] e [/bold] que quebrariam markup",
            brain,
            conn,
        )
    finally:
        conn.close()
    monkeypatch.chdir(brain.root)
    result = runner.invoke(app, ["review", cr.id])
    assert result.exit_code == 0, result.output
    assert cr.id in result.output


def test_page_open_with_brackets(tmp_path: Path, monkeypatch) -> None:
    brain = _brain(tmp_path)
    p = brain.wiki / "concepts" / "y.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Y\ntexto com [marcador] e [/x] arbitrário\n", encoding="utf-8")
    monkeypatch.chdir(brain.root)
    result = runner.invoke(app, ["page", "open", "wiki/concepts/y.md"])
    assert result.exit_code == 0, result.output
    assert "marcador" in result.output
