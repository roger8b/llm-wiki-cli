from __future__ import annotations

from llmwiki.agents.backend import ChangeRequestBackend
from llmwiki.agents.models import MaintenanceResult, QueryResult, SuggestedPage
from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import LintFinding, Severity
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import lint_service, maintenance_service, query_service


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


class TestAsk:
    def test_answer_without_save(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, question, save):
            return QueryResult(answer="RAG recupera trechos.", citations=[])

        conn = get_connection(brain.db_path)
        try:
            result, cr = query_service.ask(
                "o que é RAG?", brain, conn, _cfg(brain), save=False, runner=runner
            )
        finally:
            conn.close()
        assert "RAG" in result.answer
        assert cr is None

    def test_save_creates_cr_without_writing(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, question, save):
            return QueryResult(
                answer="resposta",
                suggested_page=SuggestedPage(
                    path="wiki/synthesis/rag-vs-wiki.md",
                    content="---\ntitle: RAG vs Wiki\ntype: synthesis\n---\n# Comparação\n",
                ),
            )

        conn = get_connection(brain.db_path)
        try:
            result, cr = query_service.ask(
                "RAG vs wiki?", brain, conn, _cfg(brain), save=True, runner=runner
            )
        finally:
            conn.close()
        assert cr is not None
        assert cr.files_changed == 1
        # não escreveu direto
        assert not (brain.root / "wiki/synthesis/rag-vs-wiki.md").exists()


class TestLintAll:
    def test_combines_structural_and_semantic(self, brain: BrainPaths) -> None:
        # cria uma página órfã (estrutural)
        p = brain.wiki / "concepts" / "x.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntitle: X\ntype: concept\n---\n# X\n", encoding="utf-8")

        def sem_runner(cfg):
            return [LintFinding(kind="contradiction", severity=Severity.error, message="A vs B")]

        findings = lint_service.lint_all(
            brain, _cfg(brain), semantic=True, semantic_runner=sem_runner
        )
        kinds = {f.kind for f in findings}
        assert "orphan_page" in kinds
        assert "contradiction" in kinds


class TestMaintain:
    def test_creates_cr_from_findings(self, brain: BrainPaths) -> None:
        findings = [LintFinding(kind="broken_link", message="x", pages=["wiki/a.md"])]

        def runner(cfg, backend: ChangeRequestBackend, *, findings_text):
            backend.write(
                "wiki/concepts/faltante.md",
                "---\ntitle: Faltante\ntype: concept\n---\n# Faltante\n",
            )
            return MaintenanceResult(summary="stub", fixed=["wiki/concepts/faltante.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = maintenance_service.maintain(findings, brain, conn, _cfg(brain), runner=runner)
        finally:
            conn.close()
        assert cr is not None
        assert cr.files_changed == 1

    def test_no_findings_returns_none(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            cr = maintenance_service.maintain([], brain, conn, _cfg(brain))
        finally:
            conn.close()
        assert cr is None
