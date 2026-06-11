"""Functional concurrency tests: real JobWorker + a concurrent CLI ingest.

Reproduces the production setup that surfaced "database is locked": the desktop
app's background ``JobWorker`` processing a job on the active brain while a
separate ``wiki ingest`` writes the same brain DB. The LLM is replaced with a
deterministic fake runner; everything else (connections, repos, change-request
creation, job lifecycle) is the real code path.
"""

from __future__ import annotations

import json
import time

import pytest

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import ingest_service
from llmwiki.workers.runner import JobWorker


def _make_source(brain: BrainPaths, name: str, text: str) -> str:
    """Write a raw source file and return its brain-relative path."""
    src = brain.raw / "articles" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(text, encoding="utf-8")
    return brain.relative(src)


def _fake_runner_factory(page_path: str, *, delay: float = 0.0):
    """Build a deterministic runner that 'writes' one page after an optional delay.

    The delay stands in for the long LLM call, widening the window in which the
    worker and the CLI writer overlap on the same DB.
    """

    def runner(cfg, backend: ChangeRequestBackend, *, source_path, source_text, source_meta=None):
        if delay:
            time.sleep(delay)
        backend.write(
            page_path,
            f"---\ntitle: P\ntype: concept\nsources: [{source_path}]\n---\n# P\nx\n",
        )
        return IngestionResult(summary="wrote page", new_pages=[page_path])

    return runner


def _wait_for_job(brain: BrainPaths, job_id: int, status: str, timeout: float = 20.0) -> dict:
    """Poll the jobs table (own connection) until job reaches status or timeout."""
    deadline = time.monotonic() + timeout
    conn = get_connection(brain.db_path, apply_schema=False)
    try:
        while time.monotonic() < deadline:
            row = JobRepo(conn).get(job_id)
            if row is not None and row["status"] == status:
                return dict(row)
            time.sleep(0.05)
        row = JobRepo(conn).get(job_id)
        raise AssertionError(
            f"job {job_id} did not reach '{status}' in {timeout}s "
            f"(last status: {row['status'] if row else None})"
        )
    finally:
        conn.close()


class TestWorkerAndCliConcurrency:
    def test_worker_job_and_cli_ingest_share_db_without_locking(
        self, brain: BrainPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Worker processes an ingest job while the CLI ingests another source.

        Both write the same WAL DB concurrently. Expect: both change requests
        created, the worker job reaches 'done', and no "database is locked".
        """
        # Worker calls ingest without a runner kwarg -> patch the default runner.
        # It sleeps so the worker is still inside its job when the CLI writes.
        worker_src = _make_source(brain, "worker.md", "worker source")
        monkeypatch.setattr(
            ingest_service,
            "_default_runner",
            _fake_runner_factory("wiki/concepts/worker.md", delay=0.5),
        )

        # Enqueue the worker's ingest job.
        enqueue_conn = get_connection(brain.db_path)
        try:
            job_id = JobRepo(enqueue_conn).create(
                "ingest", json.dumps({"source": worker_src})
            )
        finally:
            enqueue_conn.close()

        worker = JobWorker()
        worker.start()
        try:
            # Give the worker a moment to pick up the job and enter its LLM call.
            _wait_for_job(brain, job_id, "running", timeout=5.0)

            # Meanwhile, run a CLI-style ingest on a different source, same DB.
            cli_src_rel = _make_source(brain, "cli.md", "cli source")
            cli_src = brain.root / cli_src_rel
            cfg = WorkspaceConfig(brain_root=brain.root)
            conn = get_connection(brain.db_path)
            try:
                cr_cli = ingest_service.ingest(
                    cli_src,
                    brain,
                    conn,
                    cfg,
                    runner=_fake_runner_factory("wiki/concepts/cli.md"),
                )
            finally:
                conn.close()

            assert cr_cli.files_changed == 1

            # Worker job must complete cleanly (no lock error recorded).
            done = _wait_for_job(brain, job_id, "done", timeout=20.0)
            assert done["error"] is None
        finally:
            worker.stop()
            worker.join(timeout=5)

        # Both change requests landed.
        conn = get_connection(brain.db_path, apply_schema=False)
        try:
            n_crs = conn.execute("SELECT COUNT(*) FROM change_requests").fetchone()[0]
        finally:
            conn.close()
        assert n_crs == 2

    def test_repeated_cli_ingests_while_worker_polls(
        self, brain: BrainPaths
    ) -> None:
        """Worker idles (no jobs) holding its long-lived connection while the CLI
        runs several ingests back to back. None should hit a lock."""
        worker = JobWorker()
        worker.start()
        try:
            time.sleep(0.3)  # let the worker open its connection and start polling
            cfg = WorkspaceConfig(brain_root=brain.root)
            conn = get_connection(brain.db_path)
            try:
                for i in range(5):
                    src_rel = _make_source(brain, f"a{i}.md", f"source {i}")
                    cr = ingest_service.ingest(
                        brain.root / src_rel,
                        brain,
                        conn,
                        cfg,
                        runner=_fake_runner_factory(f"wiki/concepts/a{i}.md"),
                    )
                    assert cr.files_changed == 1
            finally:
                conn.close()
        finally:
            worker.stop()
            worker.join(timeout=5)

        conn = get_connection(brain.db_path, apply_schema=False)
        try:
            n_crs = conn.execute("SELECT COUNT(*) FROM change_requests").fetchone()[0]
        finally:
            conn.close()
        assert n_crs == 5
