from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from llmwiki.core.models import Page, PageType, Source, SourceStatus
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import LinkRepo, PageFtsRepo, PageRepo, SourceRepo


@pytest.fixture
def conn(tmp_path: Path):
    c = get_connection(tmp_path / "db.sqlite")
    yield c
    c.close()


class TestConnectionPragmas:
    def test_wal_and_busy_timeout(self, tmp_path: Path) -> None:
        c = get_connection(tmp_path / "db.sqlite")
        try:
            assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            c.close()


class TestSourceRepo:
    def test_upsert_and_get_by_path(self, conn) -> None:
        repo = SourceRepo(conn)
        src = Source(
            path="raw/a.md", type="md", hash="abc",
            added_at=datetime.now(UTC),
        )
        saved = repo.upsert(src)
        assert saved.id is not None
        assert repo.get_by_path("raw/a.md") is not None

    def test_get_by_hash_dedup(self, conn) -> None:
        repo = SourceRepo(conn)
        repo.upsert(Source(path="raw/a.md", type="md", hash="h1", added_at=datetime.now(UTC)))
        assert repo.get_by_hash("h1") is not None
        assert repo.get_by_hash("nope") is None

    def test_mark_processed(self, conn) -> None:
        repo = SourceRepo(conn)
        repo.upsert(
            Source(path="raw/a.md", type="md", hash="h", added_at=datetime.now(UTC))
        )
        repo.mark_processed("raw/a.md")
        assert repo.get_by_path("raw/a.md").status == SourceStatus.processed


class TestPageRepo:
    def test_upsert_list_clear(self, conn) -> None:
        repo = PageRepo(conn)
        repo.upsert(Page(
            path="wiki/concepts/x.md", title="X", type=PageType.concept,
            tags=["t"], last_updated_at=datetime.now(UTC),
        ))
        pages = repo.list()
        assert len(pages) == 1
        assert pages[0].tags == ["t"]
        repo.clear()
        assert repo.list() == []


class TestLinkRepo:
    def test_add_dedup_and_all(self, conn) -> None:
        repo = LinkRepo(conn)
        repo.add("a.md", "b.md")
        repo.add("a.md", "b.md")  # duplicado ignorado
        assert repo.all() == [("a.md", "b.md", "wikilink")]


class TestPageFtsRepo:
    def test_search_returns_matches(self, conn) -> None:
        repo = PageFtsRepo(conn)
        repo.add("wiki/a.md", "Retrieval", "texto sobre retrieval", "[]")
        repo.add("wiki/b.md", "Outro", "nada a ver", "[]")
        results = repo.search("retrieval")
        assert results
        assert results[0][0] == "wiki/a.md"

    def test_search_empty(self, conn) -> None:
        assert PageFtsRepo(conn).search("inexistente") == []
