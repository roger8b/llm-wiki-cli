from __future__ import annotations

from pathlib import Path

from llmwiki.core.config import load_config, write_default_config
from llmwiki.core.misc import now_iso, sha256, today
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import SourceRepo
from llmwiki.sources.manager import add_source


class TestAddSource:
    def test_copies_and_registers(self, brain: BrainPaths, tmp_path: Path) -> None:
        src = tmp_path / "artigo.md"
        src.write_text("# Título Legal\nconteúdo", encoding="utf-8")
        conn = get_connection(brain.db_path)
        try:
            result = add_source(src, brain, SourceRepo(conn))
        finally:
            conn.close()
        assert result.copied is True
        assert result.already_present is False
        assert result.source.path == "raw/articles/artigo.md"
        assert result.source.title == "Título Legal"
        assert (brain.raw / "articles" / "artigo.md").exists()

    def test_dedup_same_content(self, brain: BrainPaths, tmp_path: Path) -> None:
        src = tmp_path / "a.md"
        src.write_text("mesmo conteúdo", encoding="utf-8")
        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            add_source(src, brain, repo)
            dup = tmp_path / "outro-nome.md"
            dup.write_text("mesmo conteúdo", encoding="utf-8")
            result = add_source(dup, brain, repo)
        finally:
            conn.close()
        assert result.already_present is True


class TestMisc:
    def test_sha256_deterministic(self) -> None:
        assert sha256("x") == sha256(b"x")

    def test_today_and_now_iso_format(self) -> None:
        assert len(today()) == 10
        assert "T" in now_iso()


class TestConfig:
    def test_write_and_load_defaults(self, brain: BrainPaths) -> None:
        cfg = load_config(brain)
        assert cfg.model == "ollama:llama3.1"
        assert cfg.brain_root == brain.root

    def test_load_reads_overrides(self, brain: BrainPaths) -> None:
        write_default_config(brain)
        (brain.dot / "config.yaml").write_text("model: anthropic:foo\n", encoding="utf-8")
        cfg = load_config(brain)
        assert cfg.model == "anthropic:foo"
