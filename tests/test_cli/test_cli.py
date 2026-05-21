from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from llmwiki.interfaces.cli.main import app

runner = CliRunner()


class TestInit:
    def test_creates_tree(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path / "b"), "--no-git"])
        assert result.exit_code == 0
        root = tmp_path / "b"
        assert (root / ".llmwiki" / "metadata.db").exists()
        assert (root / "wiki" / "index.md").exists()
        assert (root / "WIKI_PROTOCOL.md").exists()

    def test_refuses_existing_without_force(self, tmp_path: Path) -> None:
        runner.invoke(app, ["init", str(tmp_path / "b"), "--no-git"])
        result = runner.invoke(app, ["init", str(tmp_path / "b"), "--no-git"])
        assert result.exit_code == 1


class TestEndToEnd:
    def test_flow(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "b"
        runner.invoke(app, ["init", str(root), "--no-git"])
        monkeypatch.chdir(root)

        assert runner.invoke(app, ["page", "create", "RAG", "--type", "concept"]).exit_code == 0
        assert runner.invoke(app, ["page", "create", "LLM Wiki"]).exit_code == 0

        # adiciona link para que RAG não seja órfã
        (root / "wiki/concepts/llm-wiki.md").write_text(
            "---\ntitle: LLM Wiki\ntype: concept\n---\n# LLM Wiki\n[[RAG]]\n",
            encoding="utf-8",
        )
        assert runner.invoke(app, ["index"]).exit_code == 0
        search = runner.invoke(app, ["search", "RAG"])
        assert search.exit_code == 0
        assert "rag.md" in search.output

    def test_invalid_page_type_exits_1(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "b"
        runner.invoke(app, ["init", str(root), "--no-git"])
        monkeypatch.chdir(root)
        result = runner.invoke(app, ["page", "create", "X", "--type", "bogus"])
        assert result.exit_code == 1


class TestNoBrain:
    def test_index_without_brain_exits_1(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["index"])
        assert result.exit_code == 1
