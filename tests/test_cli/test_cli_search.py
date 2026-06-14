"""`wiki search` snippets + filters (#197)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from llmwiki.interfaces.cli.main import app

runner = CliRunner()


def _seed(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "b"
    runner.invoke(app, ["brain", "create", str(root), "--no-git"])
    monkeypatch.chdir(root)
    (root / "wiki/concepts").mkdir(parents=True, exist_ok=True)
    (root / "wiki/decisions").mkdir(parents=True, exist_ok=True)
    (root / "wiki/concepts/rag.md").write_text(
        "---\ntitle: RAG\ntype: concept\ntags: [ai, retrieval]\n---\n"
        "# RAG\nRAG retrieves relevant documents before generation.\n",
        encoding="utf-8",
    )
    (root / "wiki/decisions/use-rag.md").write_text(
        "---\ntitle: Use RAG\ntype: decision\ntags: [ai]\n---\n"
        "# Use RAG\nWe decided to adopt RAG for the assistant.\n",
        encoding="utf-8",
    )
    runner.invoke(app, ["index"])
    return root


def test_search_type_filter_and_limit(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["search", "RAG", "--type", "concept", "--limit", "3", "--json"])
    assert r.exit_code == 0
    results = json.loads(r.stdout)["results"]
    assert all(x["type"] == "concept" for x in results)
    assert any("rag.md" in x["path"] for x in results)
    assert len(results) <= 3


def test_search_tag_filter(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["search", "RAG", "--tag", "retrieval", "--json"])
    results = json.loads(r.stdout)["results"]
    assert results
    assert all("retrieval" in [t.lower() for t in x["tags"]] for x in results)


def test_search_type_and_tag_combo(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(
        app, ["search", "RAG", "--type", "decision", "--tag", "ai", "--json"]
    )
    results = json.loads(r.stdout)["results"]
    assert all(x["type"] == "decision" for x in results)


def test_search_snippet_field_present(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["search", "documents", "--json"])
    results = json.loads(r.stdout)["results"]
    assert results
    assert "snippet" in results[0]


def test_search_invalid_type_exits_2(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["search", "RAG", "--type", "bogus"])
    assert r.exit_code == 2


def test_search_no_results_exit_0(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    r = runner.invoke(app, ["search", "zzzznomatch", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.stdout)["results"] == []
