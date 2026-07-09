"""Tests for the graph (backlink) signal in hybrid search RRF (#353, epic #348).

The third RRF list re-ranks ONLY the candidates the query already matched, by
incoming-link degree (wikilink targets are stored as titles — matched by slug).
``search_graph_signal`` defaults to False = byte-identical ranking.
"""

from __future__ import annotations

import sqlite3

import pytest

from llmwiki.db.connection import get_connection
from llmwiki.db.repo import LinkRepo, PageFtsRepo, PageRepo
from llmwiki.search.service import hybrid_search


@pytest.fixture
def conn(tmp_path):
    conn = get_connection(tmp_path / "meta.db")
    yield conn
    conn.close()


def _add_page(conn: sqlite3.Connection, path: str, title: str, body: str) -> None:
    from datetime import UTC, datetime

    from llmwiki.core.models import Page, PageType

    PageRepo(conn).upsert(
        Page(
            path=path,
            title=title,
            type=PageType.concept,
            tags=[],
            confidence=None,
            last_updated_at=datetime.now(UTC),
            source_count=0,
        )
    )
    PageFtsRepo(conn).add(path, title, body, "[]")


def _seed(conn: sqlite3.Connection) -> None:
    # Two pages that both match "grafo"; hub has many backlinks, stub has none.
    _add_page(conn, "wiki/concepts/grafo-stub.md", "Grafo Stub", "grafo conteudo raso")
    _add_page(conn, "wiki/concepts/grafo-hub.md", "Grafo Hub", "grafo conteudo central")
    # An unrelated page with huge degree — must never enter the results.
    _add_page(conn, "wiki/concepts/outro.md", "Outro Tema", "nada a ver")
    links = LinkRepo(conn)
    for i in range(10):
        links.add(f"wiki/concepts/p{i}.md", "Grafo Hub")
        links.add(f"wiki/concepts/q{i}.md", "Outro Tema")


def test_default_off_is_identical(conn):
    _seed(conn)
    base = hybrid_search(conn, "grafo", limit=10)
    off = hybrid_search(conn, "grafo", limit=10, graph_signal=False)
    assert [h.path for h in base] == [h.path for h in off]


def test_graph_signal_boosts_hub_over_stub(conn):
    _seed(conn)
    # FTS alone: ranking between the two "grafo" pages is bm25-driven; with the
    # graph signal the hub (10 backlinks) must come first.
    on = hybrid_search(conn, "grafo", limit=10, graph_signal=True)
    paths = [h.path for h in on]
    assert paths[0] == "wiki/concepts/grafo-hub.md"
    assert "wiki/concepts/grafo-stub.md" in paths


def test_graph_signal_never_introduces_non_matches(conn):
    _seed(conn)
    on = hybrid_search(conn, "grafo", limit=10, graph_signal=True)
    assert "wiki/concepts/outro.md" not in [h.path for h in on]


def test_no_links_brain_identical(conn):
    _add_page(conn, "wiki/concepts/a.md", "Alpha", "grafo alpha")
    _add_page(conn, "wiki/concepts/b.md", "Beta", "grafo beta")
    off = hybrid_search(conn, "grafo", limit=10, graph_signal=False)
    on = hybrid_search(conn, "grafo", limit=10, graph_signal=True)
    assert [h.path for h in off] == [h.path for h in on]


def test_config_default_off(tmp_path):
    from llmwiki.core.config import WorkspaceConfig

    assert WorkspaceConfig(brain_root=tmp_path).search_graph_signal is False
