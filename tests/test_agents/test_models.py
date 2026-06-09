"""Tests for agent output schemas + fallback-triggered path (epic #122)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from llmwiki.llm_agents import factory
from llmwiki.llm_agents.models import (
    Citation,
    IngestionResult,
    LintFindingOut,
    LintReport,
    MaintenanceResult,
    QueryResult,
    SuggestedPage,
)


class TestSchemas:
    def test_ingestion_requires_summary(self) -> None:
        with pytest.raises(ValidationError):
            IngestionResult()  # type: ignore[call-arg]

    def test_ingestion_defaults(self) -> None:
        r = IngestionResult(summary="s")
        assert r.affected_pages == [] and r.new_pages == []

    def test_query_requires_answer(self) -> None:
        with pytest.raises(ValidationError):
            QueryResult()  # type: ignore[call-arg]

    def test_query_roundtrip(self) -> None:
        r = QueryResult(
            answer="hi",
            citations=[Citation(page="wiki/a.md", quote="q")],
            suggested_page=SuggestedPage(path="wiki/b.md", content="# B"),
        )
        again = QueryResult.model_validate(r.model_dump())
        assert again.suggested_page is not None
        assert again.suggested_page.path == "wiki/b.md"
        assert again.citations[0].page == "wiki/a.md"

    def test_lint_report_defaults_empty(self) -> None:
        assert LintReport().findings == []

    def test_lint_finding_default_severity(self) -> None:
        f = LintFindingOut(kind="dup", message="m")
        assert f.severity == "warn"
        assert f.pages == []

    def test_maintenance_defaults(self) -> None:
        m = MaintenanceResult(summary="done")
        assert m.fixed == []


class TestFallbackTriggered:
    def test_no_structured_response_builds_from_text(self) -> None:
        """Weak model returns no structured_response → text fallback, not a crash."""
        state = {"messages": [SimpleNamespace(content="recovered summary")]}
        out = factory._structured(state, IngestionResult)
        assert isinstance(out, IngestionResult)
        assert out.summary == "recovered summary"

    def test_no_messages_uses_placeholder(self) -> None:
        out = factory._structured({"messages": []}, IngestionResult)
        assert isinstance(out, IngestionResult)
        assert out.summary  # placeholder, never empty
