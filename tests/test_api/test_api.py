from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def _seed_page(brain: BrainPaths) -> None:
    p = brain.wiki / "concepts" / "rag.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: RAG\ntype: concept\n---\n# RAG\nretrieval\n", encoding="utf-8")


class TestReadEndpoints:
    def test_list_pages_after_index(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        # popula índice via endpoint graph (que reindexa) ou search
        client.get("/api/graph")
        r = client.get("/api/wiki/pages")
        assert r.status_code == 200
        assert any(p["title"] == "RAG" for p in r.json())

    def test_get_page_content(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        r = client.get("/api/wiki/pages/wiki/concepts/rag.md")
        assert r.status_code == 200
        assert r.json()["frontmatter"]["title"] == "RAG"

    def test_get_missing_page_404(self, client) -> None:
        assert client.get("/api/wiki/pages/wiki/nope.md").status_code == 404

    def test_get_page_rejects_path_traversal(self, client, brain: BrainPaths) -> None:
        # URL-encoded "../" reaches the handler raw (clients normalise plain
        # "../"). The guard must reject it so we never read outside the brain.
        secret = brain.root.parent / "secret.txt"
        secret.write_text("TOPSECRET")
        r = client.get("/api/wiki/pages/%2e%2e/secret.txt")
        assert r.status_code == 404
        assert "TOPSECRET" not in r.text

    def test_search(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        client.get("/api/graph")  # reindexa (popula FTS)
        r = client.get("/api/search", params={"q": "retrieval"})
        assert r.status_code == 200
        assert r.json()[0]["path"].endswith("rag.md")

    def test_lint_structural(self, client, brain: BrainPaths) -> None:
        _seed_page(brain)
        r = client.post("/api/lint", json={"semantic": False})
        assert r.status_code == 200
        assert "findings" in r.json()

    def test_maintain_alias(self, client, brain: BrainPaths) -> None:
        # The "Propose fixes" button POSTs /api/maintain; without the top-level
        # alias the SPA catch-all only serves GET, so POST returned 405.
        _seed_page(brain)
        r = client.post("/api/maintain", json={"semantic": False})
        assert r.status_code == 200
        assert "job_id" in r.json()


class TestPageDeletion:
    def _seed_linked(self, brain: BrainPaths) -> None:
        _seed_page(brain)  # wiki/concepts/rag.md, title RAG
        other = brain.wiki / "concepts" / "vectors.md"
        other.write_text(
            "---\ntitle: Vectors\ntype: concept\n---\n# Vectors\nSee [[RAG]] for more.\n",
            encoding="utf-8",
        )

    def test_backlinks(self, client, brain: BrainPaths) -> None:
        self._seed_linked(brain)
        r = client.get("/api/wiki/backlinks", params={"path": "wiki/concepts/rag.md"})
        assert r.status_code == 200
        paths = [b["path"] for b in r.json()["backlinks"]]
        assert "wiki/concepts/vectors.md" in paths

    def test_delete_keeps_references(self, client, brain: BrainPaths) -> None:
        self._seed_linked(brain)
        r = client.post(
            "/api/wiki/delete",
            json={"path": "wiki/concepts/rag.md", "unlink_backlinks": False},
        )
        assert r.status_code == 200
        assert r.json()["files_changed"] == 1  # only the page deletion

    def test_delete_unlinks_references(self, client, brain: BrainPaths) -> None:
        self._seed_linked(brain)
        r = client.post(
            "/api/wiki/delete",
            json={"path": "wiki/concepts/rag.md", "unlink_backlinks": True},
        )
        assert r.status_code == 200
        assert r.json()["files_changed"] == 2  # deletion + rewritten backlink

    def test_delete_missing_404(self, client) -> None:
        r = client.post("/api/wiki/delete", json={"path": "wiki/nope.md"})
        assert r.status_code == 404


class TestAskHistory:
    def test_history_empty(self, client) -> None:
        r = client.get("/api/ask/history")
        assert r.status_code == 200
        assert r.json() == []

    def test_promote_creates_cr_and_links_history(
        self, client, brain: BrainPaths
    ) -> None:
        from llmwiki.db.connection import get_connection
        from llmwiki.db.repo import AskHistoryRepo

        conn = get_connection(brain.db_path)
        hid = AskHistoryRepo(conn).insert("What is RAG?", "RAG combines **retrieval**.")
        conn.close()

        r = client.post(
            "/api/ask/promote",
            json={
                "question": "What is RAG?",
                "answer": "RAG combines **retrieval**.",
                "history_id": hid,
            },
        )
        assert r.status_code == 200
        cr_id = r.json()["change_request_id"]
        assert cr_id

        # The history row is now linked to the created change request.
        items = client.get("/api/ask/history").json()
        assert items[0]["change_request_id"] == cr_id

    def test_delete_and_clear(self, client, brain: BrainPaths) -> None:
        from llmwiki.db.connection import get_connection
        from llmwiki.db.repo import AskHistoryRepo

        conn = get_connection(brain.db_path)
        repo = AskHistoryRepo(conn)
        a = repo.insert("q1", "a1")
        repo.insert("q2", "a2")
        conn.close()

        assert client.delete(f"/api/ask/history/{a}").status_code == 200
        assert len(client.get("/api/ask/history").json()) == 1

        assert client.delete("/api/ask/history").status_code == 200
        assert client.get("/api/ask/history").json() == []

    def test_review_ui_served(self, client) -> None:
        # GET / serves the built SPA (index.html with #root) when dist/ exists,
        # otherwise falls back to the legacy review.html. Accept either.
        r = client.get("/")
        assert r.status_code == 200
        text = r.text.lower()
        assert "<!doctype html" in text or "<html" in text
        assert 'id="root"' in r.text or "Review Changes" in r.text


class TestChangeRequestsEndpoints:
    def test_empty_list(self, client) -> None:
        r = client.get("/api/change-requests")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_missing_cr_404(self, client) -> None:
        assert client.get("/api/change-requests/CR-2026-9999").status_code == 404


class TestConfigEndpoints:
    def test_get_config(self, client) -> None:
        r = client.get("/api/config")
        assert r.status_code == 200
        body = r.json()
        assert "model" in body and "fts_limit" in body

    def test_patch_config(self, client) -> None:
        r = client.patch("/api/config", json={"model": "anthropic:claude-sonnet-4-5"})
        assert r.status_code == 200
        assert r.json()["model"] == "anthropic:claude-sonnet-4-5"
        assert client.get("/api/config").json()["model"] == "anthropic:claude-sonnet-4-5"

    def test_patch_config_partial(self, client) -> None:
        client.patch("/api/config", json={"fts_limit": 42})
        assert client.get("/api/config").json()["fts_limit"] == 42


class TestSourceMutations:
    def test_add_text_source(self, client) -> None:
        r = client.post(
            "/api/sources/text",
            json={"title": "My Note", "content": "Some body text."},
        )
        assert r.status_code == 200
        assert r.json()["path"].endswith("my-note.md")
        paths = [s["path"] for s in client.get("/api/sources").json()]
        assert any(p.endswith("my-note.md") for p in paths)

    def test_upload_source(self, client) -> None:
        r = client.post(
            "/api/sources/upload",
            files={"file": ("note.md", b"# Uploaded\nbody", "text/markdown")},
        )
        assert r.status_code == 200
        assert r.json()["path"].endswith("note.md")

    def test_list_sources_syncs_files_on_disk(self, client, brain) -> None:
        # A file present in raw/ but never registered must show up via disk-sync.
        f = brain.raw / "articles" / "orphan.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# Orphan\nbody", encoding="utf-8")
        paths = [s["path"] for s in client.get("/api/sources").json()]
        assert any(p.endswith("orphan.md") for p in paths)


class TestBrainsEndpoint:
    def test_list_brains(self, client) -> None:
        r = client.get("/api/brains")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_new_brain_scaffolds_and_registers(self, client, tmp_path) -> None:
        target = tmp_path / "fresh-brain"
        r = client.post(
            "/api/brains/create",
            json={"name": "Fresh", "path": str(target), "icon": "book", "activate": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Fresh" and body["icon"] == "book"
        # scaffolded on disk
        assert (target / ".llmwiki").exists()
        assert (target / "wiki").is_dir()
        # appears in the registry and is active
        names = [b["name"] for b in client.get("/api/brains").json()]
        assert "Fresh" in names
        assert client.get("/api/brains/active").json()["name"] == "Fresh"


class TestHealth:
    def test_health_ok(self, client) -> None:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestSetupEndpoints:
    def test_onboarding_status(self, client) -> None:
        r = client.get("/api/onboarding")
        assert r.status_code == 200
        body = r.json()
        assert "needs_onboarding" in body and "ollama" in body

    def test_cli_status_shape(self, client) -> None:
        r = client.get("/api/cli")
        assert r.status_code == 200
        body = r.json()
        for key in ("installed", "path", "on_path", "version"):
            assert key in body

    def test_config_test_unknown_provider(self, client) -> None:
        r = client.post("/api/config/test", json={"model": "bogus:x"})
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestProviders:
    def test_list_shape(self, client) -> None:
        r = client.get("/api/providers")
        assert r.status_code == 200
        body = r.json()
        for prov in ("anthropic", "openai", "google"):
            assert prov in body
            assert set(body[prov]) >= {"base_url", "model", "has_key"}

    def test_patch_base_url_and_model_no_key(self, client) -> None:
        # base_url + model are non-secret → persisted to config (no keychain write)
        r = client.patch(
            "/api/providers/openai",
            json={"base_url": "https://example.test/v1", "model": "gpt-4o"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["base_url"] == "https://example.test/v1"
        assert body["model"] == "gpt-4o"

    def test_patch_unknown_provider_400(self, client) -> None:
        r = client.patch("/api/providers/bogus", json={"model": "x"})
        assert r.status_code == 400


class TestSpaRouting:
    """SPA client routes must not collide with API routes."""

    def test_spa_route_does_not_return_json_list(self, client) -> None:
        # /sources is both an API path (/api/sources) and an SPA client route.
        # The bare /sources must NEVER return the JSON source list. When the SPA
        # is built it returns index.html (200); without a build it 404s. Either
        # is fine — what matters is it's not the API JSON.
        r = client.get("/sources")
        if r.status_code == 200:
            assert "text/html" in r.headers["content-type"]
        else:
            assert r.status_code == 404

    def test_api_sources_returns_json(self, client) -> None:
        r = client.get("/api/sources")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_brain_not_found_returns_404(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WIKI_BRAIN", str(tmp_path / "nope"))
    from llmwiki.interfaces.api.main import app

    c = TestClient(app)
    assert c.get("/api/sources").status_code == 404


class TestJobs:
    def test_list_and_get_jobs(self, client) -> None:
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        # Queue a query job
        r = client.post("/api/query", json={"question": "What is attention?", "save_as_page": False})
        assert r.status_code == 200
        body = r.json()
        assert "job_id" in body
        job_id = body["job_id"]

        # Fetch the queued job details
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        job = r.json()
        assert job["id"] == job_id
        assert job["type"] == "ask"
        assert job["status"] in ("queued", "running", "done", "error")

        # Verify it appears in the jobs list
        r = client.get("/api/jobs")
        assert any(j["id"] == job_id for j in r.json())
