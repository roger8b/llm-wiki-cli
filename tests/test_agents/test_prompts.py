"""Tests asserting critical rules are present in the agent prompts (epic #122).

These guard against prompt edits silently dropping a safety rule (e.g. the
read-only / raw-immutable / wiki-only constraints). They are intentionally
loose on wording but strict on the rule being mentioned.
"""

from __future__ import annotations

import pytest

from llmwiki.agents import factory

_PROMPTS = ["ingestion.md", "query.md", "lint.md", "maintenance.md"]


@pytest.fixture(scope="module")
def prompts() -> dict[str, str]:
    return {name: factory._prompt(name).lower() for name in _PROMPTS}


def test_all_prompts_load_non_empty(prompts: dict[str, str]) -> None:
    for name, text in prompts.items():
        assert text.strip(), f"{name} is empty"


def test_write_prompts_forbid_raw(prompts: dict[str, str]) -> None:
    # Prompts that can write must state raw/ is immutable.
    for name in ("ingestion.md", "maintenance.md"):
        assert "raw/" in prompts[name], f"{name} must mention raw/ immutability"


def test_write_prompts_scope_to_wiki(prompts: dict[str, str]) -> None:
    # Ingestion and maintenance must scope writes to wiki/ (matches the backend
    # allow-list enforced in ChangeRequestBackend).
    for name in ("ingestion.md", "maintenance.md"):
        assert "wiki/" in prompts[name], f"{name} must scope writes to wiki/"


def test_read_only_prompts_forbid_writing(prompts: dict[str, str]) -> None:
    # query and lint are read-only operations.
    for name in ("query.md", "lint.md"):
        assert "do not write" in prompts[name] or "read-only" in prompts[name], (
            f"{name} must declare it is read-only"
        )


def test_ingestion_requires_frontmatter(prompts: dict[str, str]) -> None:
    assert "frontmatter" in prompts["ingestion.md"]
