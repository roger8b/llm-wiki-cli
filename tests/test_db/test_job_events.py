"""Append-only job event log for live progress (#272)."""

from __future__ import annotations

import json

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobEventRepo, JobRepo


class TestJobEventRepo:
    def test_append_and_since(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            jid = JobRepo(conn).create("ingest", status="running")
            ev = JobEventRepo(conn)
            e1 = ev.append(jid, "step", {"name": "extracting"})
            e2 = ev.append(jid, "page_write", {"path": "wiki/concepts/rag.md", "op": "create"})
            rows = ev.since(jid, 0)
            assert [r["kind"] for r in rows] == ["step", "page_write"]
            assert json.loads(rows[0]["payload"]) == {"name": "extracting"}
            # `since` returns only newer rows (cursor semantics for SSE replay).
            assert [r["id"] for r in ev.since(jid, e1)] == [e2]
            assert ev.since(jid, e2) == []
        finally:
            conn.close()

    def test_payload_optional(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            jid = JobRepo(conn).create("ingest", status="running")
            ev = JobEventRepo(conn)
            ev.append(jid, "tool_end", None)
            row = ev.since(jid, 0)[0]
            assert row["payload"] is None
        finally:
            conn.close()

    def test_scoped_by_job(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            j1 = repo.create("ingest", status="running")
            j2 = repo.create("ingest", status="running")
            ev = JobEventRepo(conn)
            ev.append(j1, "step", {"name": "a"})
            ev.append(j2, "step", {"name": "b"})
            assert [json.loads(r["payload"])["name"] for r in ev.since(j1, 0)] == ["a"]
            assert [json.loads(r["payload"])["name"] for r in ev.since(j2, 0)] == ["b"]
        finally:
            conn.close()
