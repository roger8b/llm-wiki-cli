"""Contract tests for the ``--json`` flag on read commands (#196).

Each command with ``--json`` must print a single ``json.loads``-parseable object
to stdout, with the documented top-level keys, and never a bare array.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from llmwiki.interfaces.cli.main import app
from llmwiki.llm_agents.models import Citation, QueryResult
from llmwiki.services import query_service

runner = CliRunner()


def _seed(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "b"
    runner.invoke(app, ["brain", "create", str(root), "--no-git"])
    monkeypatch.chdir(root)
    runner.invoke(app, ["page", "create", "RAG", "--type", "concept"])
    (root / "wiki/concepts/llm-wiki.md").write_text(
        "---\ntitle: LLM Wiki\ntype: concept\n---\n# LLM Wiki\n[[RAG]]\n",
        encoding="utf-8",
    )
    runner.invoke(app, ["index"])
    return root


def _load(output: str) -> dict:
    obj = json.loads(output)
    assert isinstance(obj, dict)  # never a bare array
    return obj


def test_search_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["search", "RAG", "--json"])
    assert r.exit_code == 0
    obj = _load(r.stdout)
    assert "results" in obj and isinstance(obj["results"], list)
    if obj["results"]:
        hit = obj["results"][0]
        assert {"path", "title", "score", "source"} <= hit.keys()


def test_lint_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["lint", "--json"])
    obj = _load(r.stdout)
    assert "findings" in obj and isinstance(obj["findings"], list)
    for f in obj["findings"]:
        assert {"kind", "severity", "message"} <= f.keys()


def test_jobs_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["jobs", "--json"])
    assert r.exit_code == 0
    obj = _load(r.stdout)
    assert "jobs" in obj and isinstance(obj["jobs"], list)


def test_review_list_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["review", "--json"])
    assert r.exit_code == 0
    obj = _load(r.stdout)
    assert "pending" in obj and isinstance(obj["pending"], list)


def test_review_detail_not_found_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["review", "CR-NOPE", "--json"])
    assert r.exit_code != 0
    # Error envelope goes to stderr; stdout stays empty.
    assert r.stdout.strip() == ""


def test_log_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["log", "--json"])
    assert r.exit_code == 0
    obj = _load(r.stdout)
    assert "entries" in obj and isinstance(obj["entries"], list)


def test_ask_json(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)

    def fake_ask(question, paths, conn, cfg, *, save=False):
        result = QueryResult(
            answer="RAG retrieves documents.",
            citations=[Citation(page="wiki/concepts/rag.md")],
        )
        return result, None

    monkeypatch.setattr(query_service, "ask", fake_ask)
    r = runner.invoke(app, ["ask", "what is rag?", "--json"])
    assert r.exit_code == 0
    obj = _load(r.stdout)
    assert {"answer", "citations", "suggested_page", "change_request_id"} <= obj.keys()
    assert obj["answer"] == "RAG retrieves documents."
    assert obj["citations"][0]["page"] == "wiki/concepts/rag.md"
