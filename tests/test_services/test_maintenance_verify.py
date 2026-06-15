from __future__ import annotations

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import LintFinding, Severity
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import MaintenanceResult
from llmwiki.services import lint_service, maintenance_service


def _cfg(brain: BrainPaths, retries: int = 1) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root, agent_fix_retries=retries)


def _write(brain: BrainPaths, rel: str, text: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TestVerifyFindings:
    def test_broken_link_resolved_when_target_created(self, brain: BrainPaths) -> None:
        _write(brain, "a.md", "---\ntitle: A\ntype: concept\n---\n[[Faltante]]\n")
        f = LintFinding(kind="broken_link", message="x", pages=["wiki/a.md"])
        files = lint_service.disk_staging_files(
            brain,
            {"wiki/concepts/faltante.md": "---\ntitle: Faltante\ntype: concept\n---\nbody\n"},
        )
        verdicts = lint_service.verify_findings(
            [f], files, touched={"wiki/concepts/faltante.md"}
        )
        assert verdicts[lint_service.finding_id(f)] == "resolved"

    def test_broken_link_unresolved_when_not_fixed(self, brain: BrainPaths) -> None:
        _write(brain, "a.md", "---\ntitle: A\ntype: concept\n---\n[[Faltante]]\n")
        f = LintFinding(kind="broken_link", message="x", pages=["wiki/a.md"])
        files = lint_service.disk_staging_files(brain, {})
        verdicts = lint_service.verify_findings([f], files, touched=set())
        assert verdicts[lint_service.finding_id(f)] == "unresolved"

    def test_semantic_with_touched_page_is_unverifiable(self, brain: BrainPaths) -> None:
        f = LintFinding(
            kind="contradiction",
            severity=Severity.error,
            message="A vs B",
            pages=["wiki/a.md", "wiki/b.md"],
        )
        files = lint_service.disk_staging_files(brain, {})
        verdicts = lint_service.verify_findings([f], files, touched={"wiki/a.md"})
        assert verdicts[lint_service.finding_id(f)] == "unverifiable"

    def test_semantic_untouched_is_unresolved(self, brain: BrainPaths) -> None:
        f = LintFinding(kind="possible_duplicate", message="dup", pages=["wiki/a.md"])
        files = lint_service.disk_staging_files(brain, {})
        verdicts = lint_service.verify_findings([f], files, touched=set())
        assert verdicts[lint_service.finding_id(f)] == "unresolved"


class TestMaintainVerification:
    def test_resolved_fix_has_no_unresolved_warning(self, brain: BrainPaths) -> None:
        _write(brain, "a.md", "---\ntitle: A\ntype: concept\n---\n[[Faltante]]\n")
        findings = [LintFinding(kind="broken_link", message="x", pages=["wiki/a.md"])]

        def runner(cfg, backend: ChangeRequestBackend, *, findings_text):
            backend.write(
                "wiki/concepts/faltante.md",
                "---\ntitle: Faltante\ntype: concept\n---\nbody\n",
            )
            return MaintenanceResult(summary="ok", fixed=["wiki/concepts/faltante.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = maintenance_service.maintain(findings, brain, conn, _cfg(brain), runner=runner)
        finally:
            conn.close()
        assert cr is not None
        assert not [w for w in (cr.warnings or []) if w.startswith("unresolved:")]

    def test_unresolved_triggers_retry_and_is_persisted(self, brain: BrainPaths) -> None:
        _write(brain, "a.md", "---\ntitle: A\ntype: concept\n---\n[[Faltante]]\n")
        findings = [LintFinding(kind="broken_link", message="x", pages=["wiki/a.md"])]
        calls = {"n": 0}

        def runner(cfg, backend: ChangeRequestBackend, *, findings_text):
            calls["n"] += 1
            # Touch an unrelated page; never fixes the broken link.
            backend.write(
                "wiki/concepts/other.md",
                "---\ntitle: Other\ntype: concept\n---\n[[A]]\n",
            )
            return MaintenanceResult(summary="stub", fixed=["wiki/a.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = maintenance_service.maintain(
                findings, brain, conn, _cfg(brain, retries=2), runner=runner
            )
        finally:
            conn.close()
        assert cr is not None
        # 1 initial + 2 retries (still unresolved each round).
        assert calls["n"] == 3
        unresolved = [w for w in (cr.warnings or []) if w.startswith("unresolved:")]
        assert any("broken_link" in w and "wiki/a.md" in w for w in unresolved)

    def test_fixed_list_not_trusted(self, brain: BrainPaths) -> None:
        # Agent declares it fixed the link but did not → must be unresolved.
        _write(brain, "a.md", "---\ntitle: A\ntype: concept\n---\n[[Faltante]]\n")
        findings = [LintFinding(kind="broken_link", message="x", pages=["wiki/a.md"])]

        def runner(cfg, backend: ChangeRequestBackend, *, findings_text):
            backend.write("wiki/concepts/z.md", "---\ntitle: Z\ntype: concept\n---\n[[A]]\n")
            return MaintenanceResult(summary="lie", fixed=["wiki/a.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = maintenance_service.maintain(
                findings, brain, conn, _cfg(brain, retries=0), runner=runner
            )
        finally:
            conn.close()
        assert cr is not None
        assert any(w.startswith("unresolved:") for w in (cr.warnings or []))
