from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.misc import now_iso
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo, MetaRepo
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import MaintenanceResult
from llmwiki.services import (
    change_request_service,
    curator_service,
    maintenance_service,
)
from llmwiki.workers import scheduler


def _cfg(brain: BrainPaths, **kw) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root, curation_semantic=False, **kw)


def _write(brain: BrainPaths, rel: str, text: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TestRunCuration:
    def test_clean_wiki_proposes_nothing(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/a.md", "---\ntitle: A\ntype: concept\n---\n# A\n[[B]]\n")
        _write(brain, "concepts/b.md", "---\ntitle: B\ntype: concept\n---\n# B\n[[A]]\n")
        conn = get_connection(brain.db_path)
        try:
            report = curator_service.run_curation(brain, conn, _cfg(brain))
        finally:
            conn.close()
        assert report.change_requests == []
        assert report.autolink_mentions == 0
        # last_curation persisted even on a no-op run.
        assert report.ran_at

    def test_runs_steps_and_proposes_crs(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # broken_link finding + an autolinkable mention of "RAG".
        _write(brain, "concepts/rag.md", "---\ntitle: RAG\ntype: concept\n---\n# RAG\n")
        _write(brain, "concepts/a.md", "---\ntitle: A\ntype: concept\n---\n[[Missing]]\nuses RAG\n")

        def fake_fix(cfg, backend: ChangeRequestBackend, *, findings_text):
            backend.write(
                "wiki/concepts/missing.md",
                "---\ntitle: Missing\ntype: concept\n---\n# Missing\n",
            )
            return MaintenanceResult(summary="fix", fixed=["wiki/concepts/missing.md"])

        monkeypatch.setattr(maintenance_service, "_default_runner", fake_fix)

        conn = get_connection(brain.db_path)
        try:
            report = curator_service.run_curation(brain, conn, _cfg(brain))
        finally:
            conn.close()
        # A maintenance CR and an auto-link CR were proposed (never applied).
        assert len(report.change_requests) >= 1
        assert report.autolink_mentions >= 1
        assert report.findings_total >= 1

    def test_finding_with_pending_cr_not_reproposed(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(brain, "concepts/a.md", "---\ntitle: A\ntype: concept\n---\n[[Missing]]\n")
        conn = get_connection(brain.db_path)
        try:
            # Pre-existing pending CR touching wiki/concepts/a.md.
            backend = ChangeRequestBackend(brain.root)
            backend.write("wiki/concepts/a.md", "---\ntitle: A\ntype: concept\n---\nfixed\n")
            change_request_service.create_from_changes(
                backend.collect_changes(), "pre", brain, conn
            )

            called = {"n": 0}

            def fake_fix(cfg, b, *, findings_text):
                called["n"] += 1
                return MaintenanceResult(summary="x", fixed=[])

            monkeypatch.setattr(maintenance_service, "_default_runner", fake_fix)
            report = curator_service.run_curation(brain, conn, _cfg(brain))
        finally:
            conn.close()
        # The broken_link on a.md is already covered → maintenance gets nothing.
        assert report.findings_already_covered >= 1
        assert called["n"] == 0


class TestScheduler:
    def test_curation_due(self) -> None:
        now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
        assert scheduler.curation_due(None, 24, now=now) is True
        recent = (now - timedelta(hours=1)).isoformat()
        assert scheduler.curation_due(recent, 24, now=now) is False
        old = (now - timedelta(hours=48)).isoformat()
        assert scheduler.curation_due(old, 24, now=now) is True
        assert scheduler.curation_due(old, 0, now=now) is False

    def test_maybe_enqueue_when_due(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            cfg = _cfg(brain, curation_interval_hours=24)
            jid = scheduler.maybe_enqueue_curation(brain, conn, cfg)
            assert jid is not None
            # A second call must not enqueue while one is pending.
            assert scheduler.maybe_enqueue_curation(brain, conn, cfg) is None
        finally:
            conn.close()

    def test_no_enqueue_when_disabled(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            cfg = _cfg(brain, curation_interval_hours=None)
            assert scheduler.maybe_enqueue_curation(brain, conn, cfg) is None
        finally:
            conn.close()

    def test_no_enqueue_when_recent(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            MetaRepo(conn).set(curator_service.LAST_CURATION_KEY, now_iso())
            cfg = _cfg(brain, curation_interval_hours=24)
            assert scheduler.maybe_enqueue_curation(brain, conn, cfg) is None
            assert JobRepo(conn).list() == []
        finally:
            conn.close()
