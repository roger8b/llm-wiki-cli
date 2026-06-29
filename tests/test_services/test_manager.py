from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core.config import load_config
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
        import llmwiki.core.paths as _paths_mod

        # Config is now global — write directly to ~/.wiki/config.yaml
        cfg_path = _paths_mod.WIKI_HOME / "config.yaml"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text("model: anthropic:foo\n", encoding="utf-8")
        cfg = load_config(brain)
        assert cfg.model == "anthropic:foo"


class TestRemoveSource:
    """#310 — delete a non-ingested source from disk and DB."""

    def test_removes_file_and_db_row(self, brain: BrainPaths, tmp_path: Path) -> None:
        from llmwiki.sources.manager import remove_source

        src = tmp_path / "excluir.md"
        src.write_text("conteudo descartavel", encoding="utf-8")
        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            add_source(src, brain, repo)
            assert (brain.raw / "articles" / "excluir.md").exists()
            assert repo.get_by_path("raw/articles/excluir.md") is not None

            remove_source("raw/articles/excluir.md", brain, repo)
        finally:
            conn.close()

        # File gone from raw/, row gone from DB.
        assert not (brain.raw / "articles" / "excluir.md").exists()
        conn2 = get_connection(brain.db_path)
        try:
            assert SourceRepo(conn2).get_by_path("raw/articles/excluir.md") is None
        finally:
            conn2.close()

    def test_rejects_processed_source(self, brain: BrainPaths, tmp_path: Path) -> None:
        """#310 AC3: backend must refuse deletion of an already-ingested source.
        The manager raises a typed error; the API layer maps it to 409.
        """
        from llmwiki.core.errors import SourceAlreadyIngestedError
        from llmwiki.sources.manager import remove_source

        src = tmp_path / "done.md"
        src.write_text("ja foi ingerido", encoding="utf-8")
        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            add_source(src, brain, repo)
            repo.mark_processed("raw/articles/done.md")

            with pytest.raises(SourceAlreadyIngestedError):
                remove_source("raw/articles/done.md", brain, repo)
        finally:
            conn.close()
        # File must still exist — the guard fires before unlink.
        assert (brain.raw / "articles" / "done.md").exists()

    def test_missing_row_raises_not_found(self, brain: BrainPaths) -> None:
        """#310: deleting a non-existent source is a 404, not a silent no-op.
        The manager raises NotFoundError; the API maps it to 404.
        """
        from llmwiki.core.errors import NotFoundError
        from llmwiki.sources.manager import remove_source

        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            with pytest.raises(NotFoundError):
                remove_source("raw/never-existed.md", brain, repo)
        finally:
            conn.close()

    def test_rejects_path_traversal(self, brain: BrainPaths, tmp_path: Path) -> None:
        """#310 AC5: a path that escapes the brain must be rejected.
        resolve_input raises — the manager surfaces that as a typed error.
        """
        from llmwiki.core.errors import PathOutsideBrainError
        from llmwiki.sources.manager import remove_source

        conn = get_connection(brain.db_path)
        try:
            repo = SourceRepo(conn)
            with pytest.raises(PathOutsideBrainError):
                remove_source("../escape/secrets.md", brain, repo)
        finally:
            conn.close()
