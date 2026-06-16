from __future__ import annotations

import json
import os

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.workers import lifecycle


class TestServerLock:
    def test_write_read_remove(self, brain: BrainPaths) -> None:
        lifecycle.write_lock(brain, pid=4242, port=8123)
        lock = lifecycle.read_lock(brain)
        assert lock is not None
        assert lock.pid == 4242
        assert lock.port == 8123
        lifecycle.remove_lock(brain)
        assert lifecycle.read_lock(brain) is None

    def test_write_defaults_to_current_pid(self, brain: BrainPaths) -> None:
        lifecycle.write_lock(brain)
        lock = lifecycle.read_lock(brain)
        assert lock is not None and lock.pid == os.getpid()
        assert lock.port is None

    def test_read_missing_returns_none(self, brain: BrainPaths) -> None:
        assert lifecycle.read_lock(brain) is None

    def test_read_corrupt_returns_none(self, brain: BrainPaths) -> None:
        path = lifecycle.lock_path(brain)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        assert lifecycle.read_lock(brain) is None

    def test_pid_alive(self) -> None:
        assert lifecycle.pid_alive(os.getpid()) is True
        # A very high pid is almost certainly free.
        assert lifecycle.pid_alive(2_000_000_000) is False
        assert lifecycle.pid_alive(0) is False


class TestRecoverInterruptedJobs:
    def test_marks_running_as_interrupted(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            jid = repo.create("ingest", json.dumps({"source": "raw/x.md"}), status="running")
            done = repo.create("ask", "{}", status="queued")
            repo.complete(done)  # -> done
            n = lifecycle.recover_interrupted_jobs(conn)
            assert n == 1
            assert repo.get(jid)["status"] == "interrupted"
            # Already-terminal jobs untouched.
            assert repo.get(done)["status"] == "done"
        finally:
            conn.close()

    def test_no_running_jobs_is_noop(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            assert lifecycle.recover_interrupted_jobs(conn) == 0
        finally:
            conn.close()
