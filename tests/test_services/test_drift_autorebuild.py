"""Tests for drift detection + auto-rebuild at startup (#308).

The startup helper (`services.drift.detect_and_handle_drift`) is invoked from
the API ``_on_startup`` hook. It is the cheap half of the loop:

1. Compare ``count(.md em paths.wiki)`` vs ``count(wiki_pages)``.
2. If ``drift != 0`` and ``cfg.index_autorebuild_on_drift``: enqueue an
   ``index`` job (cheap — same INSERT the ``POST /api/index/reindex`` endpoint
   uses; the heavy work runs in the worker, never in the lifespan).
3. Else: persist ``index_drift_stale=true`` (plus disk/db counts) to ``meta``
   so the UI / CLI can render a "stale, run reindex" badge.
4. Always log ``WARN index drift detected: disk=N db=M ...`` (or the
   ``drift=0`` info line).

These tests exercise the helper directly — no FastAPI lifespan needed.
"""

from __future__ import annotations

import json
import logging
import time

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo, MetaRepo


def _seed_wiki_pages(brain: BrainPaths, names: list[str]) -> None:
    for n in names:
        p = brain.wiki / "concepts" / f"{n}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"---\ntitle: {n.title()}\ntype: concept\n---\n# {n.title()}\nbody\n",
            encoding="utf-8",
        )


class TestDriftDetection:
    """AC1: detect drift without blocking boot — counts only, no reindex."""

    def test_in_sync_brain_logs_zero_drift_no_job(
        self, brain: BrainPaths, caplog
    ) -> None:
        """No drift → no job queued, no meta kv written, log is INFO level."""
        _seed_wiki_pages(brain, ["rag", "vectors"])
        # Populate the index so disk == db.
        from llmwiki.services import index_service

        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, WorkspaceConfig(brain_root=brain.root))
        finally:
            conn.close()

        cfg = WorkspaceConfig(brain_root=brain.root)
        conn = get_connection(brain.db_path)
        try:
            with caplog.at_level(logging.INFO, logger="llmwiki.services.drift"):
                from llmwiki.services.drift import detect_and_handle_drift

                detect_and_handle_drift(brain, conn, cfg)
                n_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                stale = MetaRepo(conn).get("index_drift_stale")
        finally:
            conn.close()

        assert n_jobs == 0
        assert stale == "false"
        assert any("drift=0" in r.message for r in caplog.records)

    def test_disk_exceeds_db_detects_positive_drift(
        self, brain: BrainPaths
    ) -> None:
        """AC3: 3 .md on disk, 0 in db → drift=3, stale flag persisted when
        auto-rebuild is OFF."""
        _seed_wiki_pages(brain, ["one", "two", "three"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=False)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
            stale = MetaRepo(conn).get("index_drift_stale")
            assert stale == "true"
            assert MetaRepo(conn).get("index_drift_disk") == "3"
            assert MetaRepo(conn).get("index_drift_db") == "0"
        finally:
            conn.close()

    def test_db_exceeds_disk_detects_negative_drift(
        self, brain: BrainPaths
    ) -> None:
        """The drift is signed (disk - db); stale fires on either side."""
        # Build a wiki page then delete it from disk (db still has it).
        _seed_wiki_pages(brain, ["rag"])
        from llmwiki.services import index_service

        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, WorkspaceConfig(brain_root=brain.root))
            (brain.wiki / "concepts" / "rag.md").unlink()
        finally:
            conn.close()

        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=False)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
            stale = MetaRepo(conn).get("index_drift_stale")
            assert stale == "true"
            assert MetaRepo(conn).get("index_drift_disk") == "0"
            assert MetaRepo(conn).get("index_drift_db") == "1"
        finally:
            conn.close()


class TestAutoRebuildFlag:
    """AC2: with index_autorebuild_on_drift=True, an 'index' job is enqueued."""

    def test_true_enqueues_index_job(self, brain: BrainPaths) -> None:
        _seed_wiki_pages(brain, ["alpha", "beta", "gamma", "delta"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=True)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
            row = JobRepo(conn).list(limit=5)
        finally:
            conn.close()
        assert len(row) == 1
        job = row[0]
        assert job["type"] == "index"
        assert json.loads(job["payload"]).get("embeddings") is True

    def test_true_persists_stale_too_for_ui_visibility(
        self, brain: BrainPaths
    ) -> None:
        """AC2+#308 cross-ref: the front-end still needs to know the brain is
        stale while the auto-rebuild runs, so the stale meta kv is written
        regardless of the flag."""
        _seed_wiki_pages(brain, ["x"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=True)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
            stale = MetaRepo(conn).get("index_drift_stale")
        finally:
            conn.close()
        assert stale == "true"

    def test_false_persists_stale_and_does_not_enqueue(
        self, brain: BrainPaths
    ) -> None:
        """AC3: with auto-rebuild off, the stale flag is the only signal —
        no job, no implicit reindex."""
        _seed_wiki_pages(brain, ["x", "y"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=False)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
            n_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            stale = MetaRepo(conn).get("index_drift_stale")
        finally:
            conn.close()
        assert n_jobs == 0
        assert stale == "true"

    def test_in_sync_with_true_enqueues_nothing(
        self, brain: BrainPaths
    ) -> None:
        """Drift=0 → no job, no stale flag even when the flag is True."""
        _seed_wiki_pages(brain, ["rag"])
        from llmwiki.services import index_service

        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, WorkspaceConfig(brain_root=brain.root))
        finally:
            conn.close()

        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=True)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
            n_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            stale = MetaRepo(conn).get("index_drift_stale")
        finally:
            conn.close()
        assert n_jobs == 0
        assert stale == "false"


class TestStartupLog:
    """AC4: an informative log line carries the disk/db numbers."""

    def test_logs_warn_with_disk_and_db_when_stale(
        self, brain: BrainPaths, caplog
    ) -> None:
        _seed_wiki_pages(brain, ["a", "b", "c"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=False)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            with caplog.at_level(logging.INFO, logger="llmwiki.services.drift"):
                detect_and_handle_drift(brain, conn, cfg)
        finally:
            conn.close()

        # The log line includes the disk/db numbers so on-call sees them
        # without having to query the status endpoint.
        msg = " ".join(r.message for r in caplog.records)
        assert "disk=3" in msg and "db=0" in msg

    def test_logs_when_job_is_enqueued(
        self, brain: BrainPaths, caplog
    ) -> None:
        _seed_wiki_pages(brain, ["a", "b"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=True)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            with caplog.at_level(logging.INFO, logger="llmwiki.services.drift"):
                detect_and_handle_drift(brain, conn, cfg)
                job_id = JobRepo(conn).list(limit=1)[0]["id"]
        finally:
            conn.close()

        msg = " ".join(r.message for r in caplog.records)
        assert f"job #{job_id}" in msg
        assert "enqueued reindex" in msg


class TestBootLatency:
    """AC5: the drift check is two COUNTs — boot must not regress meaningfully."""

    def test_helper_completes_in_under_100ms_for_1000_files(
        self, brain: BrainPaths
    ) -> None:
        """1k markdown files on disk + populated wiki_pages — one call under 100ms.

        The bound is generous on purpose (CI variance) — the AC is that the
        helper is bounded by a few SQL COUNTs, not a reindex.  A 100ms ceiling
        for 1k files is well within "two cheap COUNTs".
        """
        # Seed 1000 .md files.
        (brain.wiki / "concepts").mkdir(parents=True, exist_ok=True)
        for i in range(1000):
            (brain.wiki / "concepts" / f"p{i}.md").write_text(
                f"---\ntitle: P{i}\ntype: concept\n---\n# P{i}\nbody\n",
                encoding="utf-8",
            )
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=False)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            t0 = time.monotonic()
            detect_and_handle_drift(brain, conn, cfg)
            elapsed = time.monotonic() - t0
        finally:
            conn.close()
        assert elapsed < 0.1, f"helper took {elapsed:.3f}s for 1k files — too slow"

    def test_helper_does_not_call_reindex(
        self, brain: BrainPaths, monkeypatch
    ) -> None:
        """Guardrail: even on a stale brain the helper must NOT invoke reindex
        (would block boot for large brains). The job-queue path is the only
        recovery surface; an inline reindex would silently reintroduce the
        very bug #308 exists to prevent."""
        from llmwiki.services import index_service

        called = {"n": 0}
        orig = index_service.reindex

        def spy(paths, conn, cfg=None):
            called["n"] += 1
            return orig(paths, conn, cfg)

        monkeypatch.setattr(index_service, "reindex", spy)

        _seed_wiki_pages(brain, ["x"])
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=True)
        conn = get_connection(brain.db_path)
        try:
            from llmwiki.services.drift import detect_and_handle_drift

            detect_and_handle_drift(brain, conn, cfg)
        finally:
            conn.close()
        assert called["n"] == 0, "drift helper must never invoke reindex inline"

def _seed_malformed(brain: BrainPaths, name: str) -> None:
    """A .md whose frontmatter is a YAML list, not a mapping → reindex skips it
    (InvalidFrontmatterError) so it lands on disk but never in wiki_pages."""
    p = brain.wiki / "concepts" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n- not\n- a mapping\n---\nbody\n", encoding="utf-8")


class TestSkippedPagesDoNotLoop:
    """#317: a malformed page must not read as eternal drift → reindex loop."""

    def test_skipped_pages_excluded_from_drift_after_reindex(
        self, brain: BrainPaths
    ) -> None:
        from llmwiki.services import index_service
        from llmwiki.services.drift import detect_and_handle_drift

        _seed_wiki_pages(brain, ["rag", "vectors"])  # 2 valid
        _seed_malformed(brain, "broken")  # 1 skipped
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=True)

        conn = get_connection(brain.db_path)
        try:
            report = index_service.reindex(brain, conn, cfg)
            assert report.pages_indexed == 2
            assert len(report.skipped) == 1
            # disk=3, db=2, skipped=1 → drift must be 0 (not 1).
            drift = detect_and_handle_drift(brain, conn, cfg)
            n_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            stale = MetaRepo(conn).get("index_drift_stale")
        finally:
            conn.close()

        assert drift == 0
        assert stale == "false"
        assert n_jobs == 0, "malformed page must not enqueue an endless reindex"

    def test_real_wipe_still_detected_with_skipped_baseline(
        self, brain: BrainPaths
    ) -> None:
        """Regression guard: skipped accounting must not mask a real wipe."""
        from llmwiki.services import index_service
        from llmwiki.services.drift import detect_and_handle_drift

        _seed_wiki_pages(brain, ["a", "b"])
        _seed_malformed(brain, "broken")
        cfg = WorkspaceConfig(brain_root=brain.root, index_autorebuild_on_drift=False)
        conn = get_connection(brain.db_path)
        try:
            index_service.reindex(brain, conn, cfg)  # persists skipped=1
            # Simulate an external wipe of wiki_pages (the desktop-brain bug).
            conn.execute("DELETE FROM wiki_pages")
            conn.commit()
            drift = detect_and_handle_drift(brain, conn, cfg)
            stale = MetaRepo(conn).get("index_drift_stale")
        finally:
            conn.close()
        # disk=3, db=0, skipped=1 → drift=2 (the 2 valid pages), still stale.
        assert drift == 2
        assert stale == "true"


class TestStartupNeverReindexesInline:
    """#316: _on_startup enqueues a job for missing embeddings, never inline."""

    def _write_embedding_config(self, wiki_home, model: str = "ollama:fake") -> None:
        (wiki_home / "config.yaml").write_text(
            f"embedding_model: {model}\n", encoding="utf-8"
        )

    def test_empty_embeddings_enqueues_job_without_inline_reindex(
        self, brain: BrainPaths, isolated_wiki_home, monkeypatch
    ) -> None:
        import llmwiki.core.paths as paths_mod
        import llmwiki.workers.lifecycle as lifecycle
        from llmwiki.interfaces.api import main as api_main
        from llmwiki.services import index_service

        self._write_embedding_config(isolated_wiki_home)
        called = {"n": 0}
        monkeypatch.setattr(
            index_service,
            "reindex",
            lambda *a, **k: called.__setitem__("n", called["n"] + 1),
        )
        monkeypatch.setattr(paths_mod, "load_active_brain", lambda: brain)
        monkeypatch.setattr(lifecycle, "write_lock", lambda *a, **k: None)

        api_main._on_startup()

        conn = get_connection(brain.db_path)
        try:
            rows = JobRepo(conn).list(limit=5)
        finally:
            conn.close()
        assert called["n"] == 0, "_on_startup must never reindex inline (#316)"
        assert len(rows) == 1
        assert rows[0]["type"] == "index"

    def test_drift_does_not_double_enqueue_backfill(
        self, brain: BrainPaths, isolated_wiki_home, monkeypatch
    ) -> None:
        """Drift!=0 already enqueues a job (rebuilds embeddings too) → the
        embeddings backfill branch must not add a second one."""
        import llmwiki.core.paths as paths_mod
        import llmwiki.workers.lifecycle as lifecycle
        from llmwiki.interfaces.api import main as api_main

        self._write_embedding_config(isolated_wiki_home)
        _seed_wiki_pages(brain, ["one", "two", "three"])  # disk=3, db=0 → drift
        monkeypatch.setattr(paths_mod, "load_active_brain", lambda: brain)
        monkeypatch.setattr(lifecycle, "write_lock", lambda *a, **k: None)

        api_main._on_startup()

        conn = get_connection(brain.db_path)
        try:
            rows = JobRepo(conn).list(limit=5)
        finally:
            conn.close()
        assert len(rows) == 1, "drift + empty embeddings must enqueue exactly one job"
