"""Tests asserting critical rules are present in the agent prompts (epic #122).

These guard against prompt edits silently dropping a safety rule (e.g. the
read-only / raw-immutable / wiki-only constraints). They are intentionally
loose on wording but strict on the rule being mentioned.
"""

from __future__ import annotations

import pytest

from llmwiki.llm_agents import factory

_PROMPTS = ["ingestion.md", "query.md", "lint.md", "maintenance.md", "outline.md"]


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
    # query, lint and outline are read-only operations.
    for name in ("query.md", "lint.md", "outline.md"):
        assert "do not write" in prompts[name] or "read-only" in prompts[name], (
            f"{name} must declare it is read-only"
        )


def test_ingestion_requires_frontmatter(prompts: dict[str, str]) -> None:
    assert "frontmatter" in prompts["ingestion.md"]


def test_ingestion_mandates_graph_exploration(prompts: dict[str, str]) -> None:
    # #165: the agent must explore related pages before writing.
    assert "related_pages" in prompts["ingestion.md"]


def test_search_prompts_mention_semantic(prompts: dict[str, str]) -> None:
    # #170: ingestion and query must tell the agent search matches by meaning.
    for name in ("ingestion.md", "query.md"):
        assert "meaning" in prompts[name], f"{name} must mention semantic/meaning search"


def test_ingestion_mentions_duplicate_guardrail(prompts: dict[str, str]) -> None:
    # #167: the prompt must teach the read-or-confirm protocol for the dup warning.
    assert "duplicate" in prompts["ingestion.md"]


def test_ingestion_has_no_hardcoded_date(prompts: dict[str, str]) -> None:
    # The dynamic date is injected via the message (DATA DE HOJE), so the prompt
    # must not carry a literal YYYY-MM-DD that models would copy into updated_at.
    import re

    assert not re.search(r"\d{4}-\d{2}-\d{2}", prompts["ingestion.md"]), (
        "ingestion.md must not hardcode a date; use the DATA DE HOJE placeholder"
    )
