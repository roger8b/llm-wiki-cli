"""API: GET /wiki/tags + GET /wiki/pages?tag= (#189)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _page(brain: BrainPaths, rel: str, title: str, tags: list[str]) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntitle: {title}\ntype: concept\ntags: [{', '.join(tags)}]\n---\n# {title}\nx\n",
        encoding="utf-8",
    )


def test_tags_and_filter(client, brain: BrainPaths) -> None:
    _page(brain, "concepts/a.md", "A", ["rag", "ai"])
    _page(brain, "concepts/b.md", "B", ["rag"])
    client.get("/api/graph")  # triggers reindex (populates page_tags)

    tags = client.get("/api/wiki/tags").json()
    assert tags[0]["tag"] == "rag" and tags[0]["count"] == 2

    filtered = client.get("/api/wiki/pages", params={"tag": "rag"}).json()
    assert {p["path"] for p in filtered} == {
        "wiki/concepts/a.md",
        "wiki/concepts/b.md",
    }
    only_ai = client.get("/api/wiki/pages", params={"tag": "ai"}).json()
    assert [p["path"] for p in only_ai] == ["wiki/concepts/a.md"]


def test_pages_without_tag_param_lists_all(client, brain: BrainPaths) -> None:
    _page(brain, "concepts/a.md", "A", ["rag"])
    client.get("/api/graph")
    assert len(client.get("/api/wiki/pages").json()) == 1
