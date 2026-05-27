from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from llmwiki.interfaces.cli.main import app

runner = CliRunner()


class TestSkillsCli:
    def test_install_yes_list_doctor_remove(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)  # local scope resolves to cwd
        r = runner.invoke(app, ["skills", "install", "--yes"])
        assert r.exit_code == 0, r.output
        link = tmp_path / ".claude" / "skills" / "wiki-query"
        assert link.is_symlink() and (link / "SKILL.md").is_file()

        assert runner.invoke(app, ["skills", "list"]).exit_code == 0
        assert runner.invoke(app, ["skills", "doctor"]).exit_code == 0

        assert runner.invoke(app, ["skills", "remove"]).exit_code == 0
        assert not link.exists()

    def test_install_multi_agents_dedup(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(
            app, ["skills", "install", "--agents", "claude,gemini", "--scope", "local"]
        )
        assert r.exit_code == 0, r.output
        assert (tmp_path / ".claude" / "skills" / "wiki-query").is_symlink()
        assert (tmp_path / ".agents" / "skills" / "wiki-query").is_symlink()  # gemini

    def test_install_no_flags_non_tty_uses_default(self, tmp_path: Path, monkeypatch) -> None:
        # CliRunner stdin is not a TTY -> falls back to non-interactive defaults
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["skills", "install"])
        assert r.exit_code == 0, r.output
        assert (tmp_path / ".claude" / "skills" / "wiki-query").is_symlink()

    def test_install_bad_agent_exits_1(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        assert runner.invoke(app, ["skills", "install", "--agent", "bogus"]).exit_code == 1
