"""Tests for ``wiki config get/set`` (#367).

The command is the CLI surface over the same storage the API's ``GET/PATCH
/config`` uses, so a value written here must be readable there (and vice
versa). Covers scalar keys, dict keys via JSON, and the two failure modes:
unknown key and invalid value.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from llmwiki.interfaces.cli.main import app

runner = CliRunner()


def _brain(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "b"
    runner.invoke(app, ["brain", "create", str(root), "--no-git"])
    monkeypatch.chdir(root)
    return root


# --- get ---------------------------------------------------------------------


def test_get_single_key(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(app, ["config", "get", "ask_mode"])
    assert res.exit_code == 0
    assert "agent" in res.stdout


def test_get_all_keys_json(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(app, ["config", "get", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, dict)
    # every settable key is dumped, and brain_root (not a config key) is not
    assert {"ask_mode", "agent_core", "search_query_expansion", "model"} <= set(data)
    assert "brain_root" not in data


def test_get_unknown_key_fails(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(app, ["config", "get", "nope"])
    assert res.exit_code != 0
    assert "nope" in res.output


# --- set ---------------------------------------------------------------------


def test_set_scalar_roundtrips(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    assert runner.invoke(app, ["config", "set", "ask_mode", "rag"]).exit_code == 0
    res = runner.invoke(app, ["config", "get", "ask_mode", "--json"])
    assert json.loads(res.stdout) == {"ask_mode": "rag"}


def test_set_int_is_typed_not_string(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    runner.invoke(app, ["config", "set", "search_query_expansion", "3"])
    value = json.loads(
        runner.invoke(app, ["config", "get", "search_query_expansion", "--json"]).stdout
    )["search_query_expansion"]
    assert value == 3
    assert not isinstance(value, str)


def test_set_dict_key_as_json(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(
        app, ["config", "set", "max_output_tokens_by_op", '{"ingest": 2048}']
    )
    assert res.exit_code == 0
    got = json.loads(
        runner.invoke(app, ["config", "get", "max_output_tokens_by_op", "--json"]).stdout
    )
    assert got == {"max_output_tokens_by_op": {"ingest": 2048}}


def test_set_none_clears_optional(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    _brain(tmp_path, monkeypatch)
    runner.invoke(app, ["config", "set", "max_output_tokens", "2048"])
    runner.invoke(app, ["config", "set", "max_output_tokens", "null"])
    got = json.loads(
        runner.invoke(app, ["config", "get", "max_output_tokens", "--json"]).stdout
    )
    assert got == {"max_output_tokens": None}


def test_set_unknown_key_lists_valid_ones(
    tmp_path: Path, monkeypatch, isolated_wiki_home
) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(app, ["config", "set", "nope", "1"])
    assert res.exit_code != 0
    assert "ask_mode" in res.output  # error lists the valid keys


def test_set_invalid_value_rejected_and_not_persisted(
    tmp_path: Path, monkeypatch, isolated_wiki_home
) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(app, ["config", "set", "search_query_expansion", "not-an-int"])
    assert res.exit_code != 0
    got = json.loads(
        runner.invoke(app, ["config", "get", "search_query_expansion", "--json"]).stdout
    )
    assert got == {"search_query_expansion": 0}  # default preserved


def test_set_malformed_json_for_dict_key_rejected(
    tmp_path: Path, monkeypatch, isolated_wiki_home
) -> None:
    _brain(tmp_path, monkeypatch)
    res = runner.invoke(app, ["config", "set", "max_output_tokens_by_op", "{ingest: "])
    assert res.exit_code != 0


# --- same storage as the API -------------------------------------------------


def test_cli_set_is_visible_to_the_api(tmp_path: Path, monkeypatch, isolated_wiki_home) -> None:
    root = _brain(tmp_path, monkeypatch)
    runner.invoke(app, ["config", "set", "fts_limit", "42"])

    from llmwiki.core.config import load_config
    from llmwiki.core.paths import BrainPaths

    assert load_config(BrainPaths(root)).fts_limit == 42
