"""Regression tests for write-lock contention between two writers on one WAL DB.

Reproduces the "database is locked" surfaced when the CLI ingest and the desktop
JobWorker write the same brain DB concurrently. Each writer opens its own
connection (separate process in production) against the same file.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from llmwiki.db.connection import get_connection, retry_on_locked


def _busy_timeout(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA busy_timeout").fetchone()[0])


class TestConnectionTuning:
    def test_busy_timeout_is_generous(self, tmp_path: Path) -> None:
        conn = get_connection(tmp_path / "db.sqlite")
        try:
            # >= 15s so a peer's short write burst is absorbed, not failed.
            assert _busy_timeout(conn) >= 15000
        finally:
            conn.close()


class TestRetryOnLocked:
    def test_retries_then_succeeds(self) -> None:
        calls = {"n": 0}

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        assert retry_on_locked(flaky, base_delay=0.0) == "ok"
        assert calls["n"] == 3

    def test_gives_up_and_reraises(self) -> None:
        def always_locked() -> None:
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            retry_on_locked(always_locked, attempts=3, base_delay=0.0)

    def test_does_not_retry_other_errors(self) -> None:
        calls = {"n": 0}

        def boom() -> None:
            calls["n"] += 1
            raise sqlite3.OperationalError("no such table: nope")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            retry_on_locked(boom, base_delay=0.0)
        assert calls["n"] == 1  # not retried


class TestTwoWriters:
    def test_concurrent_writers_same_wal_db(self, tmp_path: Path) -> None:
        """Two threads, two connections, hammer the same WAL DB.

        With retry_on_locked + a generous busy_timeout, every write must land and
        no "database is locked" should escape.
        """
        db_path = tmp_path / "brain.sqlite"
        # First connection applies the schema (creates the jobs table).
        get_connection(db_path).close()

        writes_per_thread = 40
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def worker(tag: str) -> None:
            conn = get_connection(db_path, apply_schema=False)
            try:
                barrier.wait()  # maximise overlap
                for i in range(writes_per_thread):
                    def _do(n: int = i) -> None:
                        conn.execute(
                            "INSERT INTO jobs (type, status, payload, created_at) "
                            "VALUES (?, 'queued', ?, ?)",
                            (tag, f"{tag}-{n}", "2026-06-07T00:00:00Z"),
                        )
                        conn.commit()

                    retry_on_locked(_do)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                conn.close()

        threads = [
            threading.Thread(target=worker, args=("A",)),
            threading.Thread(target=worker, args=("B",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"writers hit errors: {errors}"

        conn = get_connection(db_path, apply_schema=False)
        try:
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        finally:
            conn.close()
        assert total == 2 * writes_per_thread

    def test_busy_timeout_waits_out_a_held_write_lock(self, tmp_path: Path) -> None:
        """A second writer blocks on busy_timeout instead of failing instantly.

        Thread A grabs the write lock and holds it ~0.3s; thread B's write must
        wait for it and then succeed, rather than raising "database is locked".
        Each connection stays on its own thread (sqlite forbids cross-thread use).
        """
        db_path = tmp_path / "brain.sqlite"
        get_connection(db_path).close()

        lock_held = threading.Event()

        def holder() -> None:
            a = get_connection(db_path, apply_schema=False)
            try:
                a.execute("BEGIN IMMEDIATE")  # grab the write lock
                a.execute(
                    "INSERT INTO jobs (type, status, created_at) VALUES ('A','queued','now')"
                )
                lock_held.set()
                time.sleep(0.3)
                a.commit()
            finally:
                a.close()

        t = threading.Thread(target=holder)
        t.start()
        assert lock_held.wait(timeout=5)

        b = get_connection(db_path, apply_schema=False)
        try:
            # B must block (busy_timeout=15s) until A commits, then succeed.
            start = time.monotonic()
            b.execute(
                "INSERT INTO jobs (type, status, created_at) VALUES ('B','queued','now')"
            )
            b.commit()
            waited = time.monotonic() - start

            assert waited >= 0.15  # actually waited for A's lock
            assert b.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
        finally:
            b.close()
            t.join(timeout=5)
