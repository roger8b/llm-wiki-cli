"""Tests for query citation validation (issue #172)."""

from __future__ import annotations

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents.models import Citation, QueryResult
from llmwiki.services import index_service, query_service


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


def _seed_page(brain: BrainPaths) -> None:
    page = brain.wiki / "concepts" / "rag.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: RAG\ntype: concept\n---\n# RAG\nbody\n", encoding="utf-8"
    )
    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn)
    finally:
        conn.close()


def _validate(brain: BrainPaths, citations: list[Citation]) -> QueryResult:
    result = QueryResult(answer="a", citations=citations)
    conn = get_connection(brain.db_path)
    try:
        query_service._validate_citations(result, brain, conn)
    finally:
        conn.close()
    return result


class TestValidateCitations:
    def test_exact_path_valid(self, brain: BrainPaths) -> None:
        _seed_page(brain)
        out = _validate(brain, [Citation(page="wiki/concepts/rag.md")])
        assert out.citations[0].invalid is False

    def test_title_resolves_and_normalizes_to_path(self, brain: BrainPaths) -> None:
        _seed_page(brain)
        out = _validate(brain, [Citation(page="RAG")])
        assert out.citations[0].invalid is False
        assert out.citations[0].page == "wiki/concepts/rag.md"

    def test_nonexistent_page_invalid(self, brain: BrainPaths) -> None:
        _seed_page(brain)
        out = _validate(brain, [Citation(page="Nonexistent Concept")])
        assert out.citations[0].invalid is True

    def test_raw_source_valid(self, brain: BrainPaths) -> None:
        src = brain.raw / "articles" / "a.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("x", encoding="utf-8")
        out = _validate(brain, [Citation(source="raw/articles/a.md")])
        assert out.citations[0].invalid is False

    def test_raw_traversal_invalid(self, brain: BrainPaths) -> None:
        out = _validate(brain, [Citation(source="raw/../../etc/passwd")])
        assert out.citations[0].invalid is True

    def test_missing_raw_source_invalid(self, brain: BrainPaths) -> None:
        out = _validate(brain, [Citation(source="raw/articles/missing.md")])
        assert out.citations[0].invalid is True

    def test_empty_citation_invalid(self, brain: BrainPaths) -> None:
        out = _validate(brain, [Citation()])
        assert out.citations[0].invalid is True


class TestAskValidatesCitations:
    def test_mixed_citations(self, brain: BrainPaths) -> None:
        _seed_page(brain)

        def runner(cfg, backend, *, question, save):
            return QueryResult(
                answer="resposta",
                citations=[Citation(page="RAG"), Citation(page="Ghost Page")],
            )

        conn = get_connection(brain.db_path)
        try:
            result, _ = query_service.ask(
                "q", brain, conn, _cfg(brain), runner=runner
            )
        finally:
            conn.close()
        assert result.citations[0].invalid is False
        assert result.citations[0].page == "wiki/concepts/rag.md"
        assert result.citations[1].invalid is True


def test_old_payload_without_invalid_loads() -> None:
    cit = Citation.model_validate({"page": "wiki/x.md", "quote": "q"})
    assert cit.invalid is False
