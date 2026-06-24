"""GET/PATCH /config exposes the new editable fields for Settings (#237)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llmwiki.core.paths import BrainPaths

NEW_FIELDS = {
    "agent_max_retries",
    "agent_fix_retries",
    "embedding_model",
    "chunk_threshold_chars",
    "chunk_size_chars",
    "chunk_overlap_chars",
    "ingest_scope_concepts_per_chunk",
    "whisper_model",
    "whisper_language",
}


@pytest.fixture
def client(brain: BrainPaths, monkeypatch):
    monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
    from llmwiki.interfaces.api.main import app

    return TestClient(app)


def test_get_config_exposes_new_fields(client) -> None:
    body = client.get("/api/config").json()
    assert NEW_FIELDS <= body.keys()
    # defaults from WorkspaceConfig
    assert body["chunk_threshold_chars"] == 24000
    assert body["ingest_scope_concepts_per_chunk"] is True
    assert body["embedding_model"] is None
    assert body["whisper_model"] == "small"


def test_patch_round_trips_new_fields(client) -> None:
    r = client.patch(
        "/api/config",
        json={
            "embedding_model": "ollama:nomic-embed-text",
            "chunk_size_chars": 9000,
            "ingest_scope_concepts_per_chunk": False,
            "agent_fix_retries": 3,
            "whisper_language": "pt",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["embedding_model"] == "ollama:nomic-embed-text"
    assert body["chunk_size_chars"] == 9000
    assert body["ingest_scope_concepts_per_chunk"] is False
    assert body["agent_fix_retries"] == 3
    assert body["whisper_language"] == "pt"
    # re-read confirms persistence
    again = client.get("/api/config").json()
    assert again["chunk_size_chars"] == 9000


def test_embedding_model_null_disables(client) -> None:
    client.patch("/api/config", json={"embedding_model": "ollama:x"})
    r = client.patch("/api/config", json={"embedding_model": None})
    assert r.json()["embedding_model"] is None
