from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from llmwiki.interfaces.cli.main import app

runner = CliRunner()


class TestBrainCreate:
    def test_creates_tree(self, tmp_path: Path) -> None:
        from llmwiki.core import brains as brains_registry

        result = runner.invoke(app, ["brain", "create", str(tmp_path / "b"), "--no-git"])
        assert result.exit_code == 0
        root = tmp_path / "b"
        # Brain is registered; its DB lives under ~/.wiki/brains/<uuid>/
        brain = brains_registry.get_active_brain()
        assert brain is not None and brain.path == str(root.resolve())
        assert brains_registry.get_brain_db_path(brain.id).exists()
        assert (root / ".llmwiki").exists()  # marker dir still in brain
        assert (root / "wiki" / "index.md").exists()
        assert (root / "WIKI_PROTOCOL.md").exists()

    def test_refuses_existing_without_force(self, tmp_path: Path) -> None:
        runner.invoke(app, ["brain", "create", str(tmp_path / "b"), "--no-git"])
        result = runner.invoke(app, ["brain", "create", str(tmp_path / "b"), "--no-git"])
        assert result.exit_code == 1


class TestInitWorkspaceRules:
    def test_init_injects_into_both_files_idempotently(self, tmp_path: Path, monkeypatch) -> None:
        brain = tmp_path / "b"
        runner.invoke(app, ["brain", "create", str(brain), "--no-git"])
        ws = tmp_path / "workspace"
        ws.mkdir()
        monkeypatch.chdir(ws)

        r = runner.invoke(app, ["init"])
        assert r.exit_code == 0
        for fn in ("AGENTS.md", "CLAUDE.md"):
            text = (ws / fn).read_text()
            assert "<!-- llm-wiki:start -->" in text
            assert "wiki ask" in text

        runner.invoke(app, ["init"])  # idempotent
        assert (ws / "AGENTS.md").read_text().count("<!-- llm-wiki:start -->") == 1

    def test_init_remove(self, tmp_path: Path, monkeypatch) -> None:
        runner.invoke(app, ["brain", "create", str(tmp_path / "b"), "--no-git"])
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.chdir(ws)
        runner.invoke(app, ["init", "--claude"])
        assert (ws / "CLAUDE.md").exists()
        r = runner.invoke(app, ["init", "--remove", "--claude"])
        assert r.exit_code == 0
        assert "<!-- llm-wiki:start -->" not in (ws / "CLAUDE.md").read_text()


class TestEndToEnd:
    def test_flow(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "b"
        runner.invoke(app, ["brain", "create", str(root), "--no-git"])
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
        runner.invoke(app, ["brain", "create", str(root), "--no-git"])
        monkeypatch.chdir(root)
        result = runner.invoke(app, ["page", "create", "X", "--type", "bogus"])
        assert result.exit_code == 1


class TestNoBrain:
    def test_index_without_brain_exits_1(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["index"])
        assert result.exit_code == 1
