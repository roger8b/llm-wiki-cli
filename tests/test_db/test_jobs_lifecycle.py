"""Tests for job progress + cancellation persistence (epic #121, #137/#138)."""

from __future__ import annotations

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo


class TestProgress:
    def test_set_and_read_progress(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            jid = repo.create("ingest", status="running")
            repo.set_progress(jid, "running_agent")
            assert repo.get(jid)["progress"] == "running_agent"
            repo.set_progress(jid, "creating_change_request")
            assert repo.get(jid)["progress"] == "creating_change_request"
        finally:
            conn.close()


class TestCancellation:
    def test_request_and_read_cancel_flag(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            jid = repo.create("ingest", status="running")
            assert repo.is_cancel_requested(jid) is False
            repo.request_cancel(jid)
            assert repo.is_cancel_requested(jid) is True
        finally:
            conn.close()

    def test_cancel_sets_terminal_state(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            jid = repo.create("ingest", status="running")
            repo.cancel(jid, result='{"cancelled": true}')
            row = repo.get(jid)
            assert row["status"] == "cancelled"
            assert row["completed_at"] is not None
        finally:
            conn.close()

    def test_cross_connection_visibility(self, brain: BrainPaths) -> None:
        """The worker reads the cancel flag on a different connection (WAL)."""
        writer = get_connection(brain.db_path)
        reader = get_connection(brain.db_path)
        try:
            jid = JobRepo(writer).create("ingest", status="running")
            JobRepo(writer).request_cancel(jid)
            assert JobRepo(reader).is_cancel_requested(jid) is True
        finally:
            writer.close()
            reader.close()
