from __future__ import annotations

from typer.testing import CliRunner

from llmwiki.core.paths import BrainPaths
from llmwiki.interfaces.cli.main import app
from llmwiki.services import ingest_service

runner = CliRunner()


def _seed(brain: BrainPaths, name: str) -> str:
    p = brain.raw / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {name}\nbody\n", encoding="utf-8")
    return f"raw/{name}"


class FakeCR:
    id = "CR-2026-0001"
    files_changed = 1
    changes: list = []


class TestIngestMulti:
    def test_failure_isolated_others_proceed(
        self, brain: BrainPaths, monkeypatch
    ) -> None:
        monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
        a = _seed(brain, "a.md")
        b = _seed(brain, "b.md")
        c = _seed(brain, "c.md")

        def fake_ingest(target, paths, conn, cfg, **kw):
            if target.name == "b.md":
                raise RuntimeError("boom")
            return FakeCR()

        monkeypatch.setattr(ingest_service, "ingest", fake_ingest)

        result = runner.invoke(app, ["ingest", a, b, c])
        # one failure -> non-zero exit, but a + c still processed
        assert result.exit_code == 1
        assert "2 ok, 1 failed" in result.stdout

    def test_all_ok_exit_zero(self, brain: BrainPaths, monkeypatch) -> None:
        monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
        a = _seed(brain, "a.md")
        b = _seed(brain, "b.md")
        monkeypatch.setattr(
            ingest_service, "ingest", lambda *a, **k: FakeCR()
        )
        result = runner.invoke(app, ["ingest", a, b])
        assert result.exit_code == 0
        assert "2 ok, 0 failed" in result.stdout

    def test_missing_file_counts_as_failure(
        self, brain: BrainPaths, monkeypatch
    ) -> None:
        monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
        a = _seed(brain, "a.md")
        monkeypatch.setattr(ingest_service, "ingest", lambda *a, **k: FakeCR())
        result = runner.invoke(app, ["ingest", a, "raw/nope.md"])
        assert result.exit_code == 1
        assert "1 ok, 1 failed" in result.stdout
