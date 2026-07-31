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


# --- #348 flags exposed for Settings (#368) ----------------------------------

ASK_FIELDS = {"ask_mode", "ask_rag_top_k", "ask_rag_max_context_chars"}


def test_get_config_exposes_ask_fields(client) -> None:
    body = client.get("/api/config").json()
    assert ASK_FIELDS <= body.keys()
    # H2 (#350) shipped opt-in: the agent loop stays the default.
    assert body["ask_mode"] == "agent"


def test_patch_round_trips_ask_fields(client) -> None:
    r = client.patch(
        "/api/config",
        json={"ask_mode": "rag", "ask_rag_top_k": 8, "ask_rag_max_context_chars": 12000},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ask_mode"] == "rag"
    assert body["ask_rag_top_k"] == 8
    assert body["ask_rag_max_context_chars"] == 12000
    again = client.get("/api/config").json()
    assert again["ask_mode"] == "rag"
    assert again["ask_rag_top_k"] == 8


# --- agent core (#369) -------------------------------------------------------


def test_get_config_exposes_agent_core(client) -> None:
    body = client.get("/api/config").json()
    assert {"agent_core", "minimal_max_turns"} <= body.keys()
    # H6 (#352) shipped opt-in: DeepAgents stays the default core.
    assert body["agent_core"] == "deepagents"
    assert body["minimal_max_turns"] == 40


def test_patch_round_trips_agent_core(client) -> None:
    r = client.patch("/api/config", json={"agent_core": "minimal", "minimal_max_turns": 60})
    assert r.status_code == 200
    assert r.json()["agent_core"] == "minimal"
    again = client.get("/api/config").json()
    assert again["agent_core"] == "minimal"
    assert again["minimal_max_turns"] == 60


# --- output cap (#370) -------------------------------------------------------


def test_get_config_exposes_output_cap(client) -> None:
    body = client.get("/api/config").json()
    assert {"max_output_tokens", "max_output_tokens_by_op"} <= body.keys()
    # H5 (#351) shipped opt-in: no cap by default.
    assert body["max_output_tokens"] is None
    assert body["max_output_tokens_by_op"] == {}


def test_patch_round_trips_output_cap(client) -> None:
    r = client.patch(
        "/api/config",
        json={"max_output_tokens": 4096, "max_output_tokens_by_op": {"ingest": 2048}},
    )
    assert r.status_code == 200
    again = client.get("/api/config").json()
    assert again["max_output_tokens"] == 4096
    assert again["max_output_tokens_by_op"] == {"ingest": 2048}


def test_patch_clearing_removes_the_per_op_key(client) -> None:
    client.patch("/api/config", json={"max_output_tokens_by_op": {"ingest": 2048}})
    r = client.patch("/api/config", json={"max_output_tokens_by_op": {}})
    assert r.status_code == 200
    assert client.get("/api/config").json()["max_output_tokens_by_op"] == {}


@pytest.mark.parametrize(
    "patch",
    [
        {"max_output_tokens": 0},
        {"max_output_tokens": -1},
        {"max_output_tokens_by_op": {"ingest": 0}},
        {"max_output_tokens_by_op": {"ingest": -5}},
    ],
)
def test_patch_rejects_non_positive_cap(client, patch) -> None:
    r = client.patch("/api/config", json=patch)
    assert r.status_code == 400
    # nothing persisted
    body = client.get("/api/config").json()
    assert body["max_output_tokens"] is None
    assert body["max_output_tokens_by_op"] == {}


def test_legacy_zero_cap_in_the_file_still_loads(brain: BrainPaths, isolated_wiki_home) -> None:
    """Configs written before #370 kept ``0`` meaning "no cap" — they must load."""
    import yaml

    from llmwiki.core.config import load_config

    cfg_file = isolated_wiki_home / "config.yaml"
    cfg_file.write_text(yaml.safe_dump({"max_output_tokens": 0}), encoding="utf-8")
    assert load_config(brain).max_output_tokens == 0


@pytest.mark.parametrize("value", [0.0, -1.0, "0", "-3", True])
def test_patch_rejects_coercible_non_positive_cap(client, value) -> None:
    """Pydantic coerces these to int, so the guard must run on validated values."""
    r = client.patch("/api/config", json={"max_output_tokens": value})
    assert r.status_code == 400
    assert client.get("/api/config").json()["max_output_tokens"] is None
