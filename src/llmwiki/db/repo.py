"""CRUD repositories over SQLite connections.

Each repository encapsulates a table. Conversions to/from domain models
happen here; the rest of the app does not write SQL.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import cast

from ..core.misc import now_iso
from ..core.models import Page, Source, SourceStatus
from .connection import retry_on_locked


class SourceRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, source: Source) -> Source:
        cur = self.conn.execute(
            """
            INSERT INTO sources (path, type, title, hash, added_at, processed_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                type=excluded.type, title=excluded.title, hash=excluded.hash,
                processed_at=excluded.processed_at, status=excluded.status
            RETURNING id
            """,
            (
                source.path,
                source.type,
                source.title,
                source.hash,
                source.added_at.isoformat()
                if hasattr(source.added_at, "isoformat")
                else source.added_at,
                source.processed_at.isoformat() if source.processed_at else None,
                source.status.value,
            ),
        )
        row = cur.fetchone()
        self.conn.commit()
        source.id = int(row["id"])
        return source

    def get_by_path(self, path: str) -> Source | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE path = ?", (path,)
        ).fetchone()
        return _row_to_source(row) if row else None

    def get_by_hash(self, digest: str) -> Source | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE hash = ? LIMIT 1", (digest,)
        ).fetchone()
        return _row_to_source(row) if row else None

    def list(self) -> list[Source]:
        rows = self.conn.execute(
            "SELECT * FROM sources ORDER BY added_at"
        ).fetchall()
        return [_row_to_source(r) for r in rows]

    def mark_processed(self, path: str) -> None:
        self.conn.execute(
            "UPDATE sources SET status = ?, processed_at = ? WHERE path = ?",
            (SourceStatus.processed.value, now_iso(), path),
        )
        self.conn.commit()


class PageRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, page: Page) -> None:
        self.conn.execute(
            """
            INSERT INTO wiki_pages
                (path, title, type, summary, tags, last_updated_at, source_count, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title, type=excluded.type, summary=excluded.summary,
                tags=excluded.tags, last_updated_at=excluded.last_updated_at,
                source_count=excluded.source_count, confidence=excluded.confidence
            """,
            (
                page.path,
                page.title,
                page.type.value,
                page.summary,
                json.dumps(page.tags),
                page.last_updated_at.isoformat()
                if hasattr(page.last_updated_at, "isoformat")
                else page.last_updated_at,
                page.source_count,
                page.confidence.value if page.confidence else None,
            ),
        )
        self.conn.commit()

    def by_type(self, ptype: str) -> list[Page]:
        rows = self.conn.execute(
            "SELECT * FROM wiki_pages WHERE type = ? ORDER BY path", (ptype,)
        ).fetchall()
        return [_row_to_page(r) for r in rows]

    def list(self) -> list[Page]:
        rows = self.conn.execute(
            "SELECT * FROM wiki_pages ORDER BY type, path"
        ).fetchall()
        return [_row_to_page(r) for r in rows]

    def clear(self) -> None:
        self.conn.execute("DELETE FROM wiki_pages")
        self.conn.commit()


class LinkRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, from_page: str, to_page: str, link_type: str = "wikilink") -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO links (from_page, to_page, link_type)
            VALUES (?, ?, ?)
            """,
            (from_page, to_page, link_type),
        )
        self.conn.commit()

    def all(self) -> list[tuple[str, str, str]]:
        rows = self.conn.execute(
            "SELECT from_page, to_page, link_type FROM links"
        ).fetchall()
        return [(r["from_page"], r["to_page"], r["link_type"]) for r in rows]

    def backlinks(self, to_page: str) -> list[str]:
        """Pages that link TO ``to_page`` (incoming links / impact set)."""
        rows = self.conn.execute(
            "SELECT from_page FROM links WHERE to_page = ? ORDER BY from_page",
            (to_page,),
        ).fetchall()
        return [r["from_page"] for r in rows]

    def outgoing(self, from_page: str) -> list[str]:
        """Pages that ``from_page`` links TO (outgoing links)."""
        rows = self.conn.execute(
            "SELECT to_page FROM links WHERE from_page = ? ORDER BY to_page",
            (from_page,),
        ).fetchall()
        return [r["to_page"] for r in rows]

    def clear(self) -> None:
        self.conn.execute("DELETE FROM links")
        self.conn.commit()


class PageFtsRepo:
    """Full-text search index (FTS5) over page bodies."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def clear(self) -> None:
        self.conn.execute("DELETE FROM pages_fts")
        self.conn.commit()

    def add(self, path: str, title: str, body: str, tags: str) -> None:
        self.conn.execute(
            "INSERT INTO pages_fts (path, title, body, tags) VALUES (?, ?, ?, ?)",
            (path, title, body, tags),
        )
        self.conn.commit()

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Make a free-form query safe for FTS5 MATCH.

        FTS5 uses a rich query syntax where hyphens, parentheses, colons, and
        operators (AND/OR/NOT) have special meaning.  LLM-generated queries often
        contain those characters and blow up with "no such column" / "syntax
        error".  Strategy: keep only alphanumeric chars + spaces, collapse
        whitespace, then OR the tokens together.
        """
        tokens = re.sub(r"[^a-zA-Z0-9À-ÿ\s]", " ", query).split()
        if not tokens:
            return '""'  # empty phrase — returns nothing gracefully
        # Join as OR query; FTS5 treats space-separated terms as AND by default,
        # so we use explicit OR for broader recall.
        return " OR ".join(tokens)

    # FTS5 snippet over the body column (index 2): 12-token window, «» highlight.
    _SNIPPET_EXPR = "snippet(pages_fts, 2, '«', '»', '…', 12)"

    @staticmethod
    def _one_line(text: str | None) -> str | None:
        """Collapse a raw-markdown snippet to a single whitespace-normalised line."""
        if not text:
            return None
        collapsed = " ".join(text.split())
        return collapsed or None

    def _run_search(
        self, query: str, limit: int, *, with_snippet: bool
    ) -> list[sqlite3.Row]:
        cols = "path, title, bm25(pages_fts) AS rank"
        if with_snippet:
            cols += f", {self._SNIPPET_EXPR} AS snippet"
        sql = (
            f"SELECT {cols} FROM pages_fts "
            "WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?"
        )
        safe_query = self._sanitize_fts_query(query)
        try:
            return self.conn.execute(sql, (safe_query, limit)).fetchall()
        except sqlite3.OperationalError:
            # Last-resort fallback: phrase search on the original query.
            return self.conn.execute(sql, (f'"{query}"', limit)).fetchall()

    def search(self, query: str, limit: int = 20) -> list[tuple[str, str, float]]:
        """Return (path, title, rank) sorted by relevance (bm25, lower = better)."""
        rows = self._run_search(query, limit, with_snippet=False)
        return [(r["path"], r["title"], float(r["rank"])) for r in rows]

    def search_snippets(
        self, query: str, limit: int = 20
    ) -> list[tuple[str, str, float, str | None]]:
        """Like :meth:`search` but also returns an FTS5 highlight snippet (#171).

        The snippet is a single line drawn from the page body with the matched
        terms wrapped in « »; ``None`` when the match is title/tags-only.
        """
        rows = self._run_search(query, limit, with_snippet=True)
        return [
            (r["path"], r["title"], float(r["rank"]), self._one_line(r["snippet"]))
            for r in rows
        ]


class JobRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, type_: str, payload: str | None = None, status: str = "queued") -> int:
        def _do() -> int:
            cur = self.conn.execute(
                "INSERT INTO jobs (type, status, payload, created_at) VALUES (?, ?, ?, ?)",
                (type_, status, payload, now_iso()),
            )
            self.conn.commit()
            return int(cur.lastrowid or 0)

        return retry_on_locked(_do)

    def get(self, job_id: int) -> sqlite3.Row | None:
        return cast(
            "sqlite3.Row | None",
            self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone(),
        )

    def complete(self, job_id: int, result: str | None = None, error: str | None = None) -> None:
        status = "error" if error else "done"

        def _do() -> None:
            self.conn.execute(
                "UPDATE jobs SET status = ?, result = ?, error = ?, completed_at = ? "
                "WHERE id = ?",
                (status, result, error, now_iso(), job_id),
            )
            self.conn.commit()

        retry_on_locked(_do)

    def cancel(self, job_id: int, result: str | None = None) -> None:
        """Mark a job as cancelled (terminal, not an error)."""

        def _do() -> None:
            self.conn.execute(
                "UPDATE jobs SET status = 'cancelled', result = ?, completed_at = ? "
                "WHERE id = ?",
                (result, now_iso(), job_id),
            )
            self.conn.commit()

        retry_on_locked(_do)

    def set_progress(self, job_id: int, step: str) -> None:
        """Record a coarse progress step for a running job (best-effort)."""

        def _do() -> None:
            self.conn.execute(
                "UPDATE jobs SET progress = ? WHERE id = ?", (step, job_id)
            )
            self.conn.commit()

        retry_on_locked(_do)

    def request_cancel(self, job_id: int) -> None:
        """Flag a job for cooperative cancellation (read by the running agent)."""

        def _do() -> None:
            self.conn.execute(
                "UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job_id,)
            )
            self.conn.commit()

        retry_on_locked(_do)

    def is_cancel_requested(self, job_id: int) -> bool:
        row = self.conn.execute(
            "SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return bool(row["cancel_requested"]) if row else False

    def list(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


class ChangeRequestRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def next_id(self) -> str:
        year = now_iso()[:4]
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM change_requests WHERE id LIKE ?",
            (f"CR-{year}-%",),
        ).fetchone()
        return f"CR-{year}-{int(row['n']) + 1:04d}"

    def insert(
        self,
        cr_id: str,
        summary: str | None,
        files_changed: int,
        diff_dir: str,
        job_id: int | None = None,
    ) -> None:
        def _do() -> None:
            self.conn.execute(
                """
                INSERT INTO change_requests
                    (id, job_id, status, summary, files_changed, diff_dir, created_at)
                VALUES (?, ?, 'pending_review', ?, ?, ?, ?)
                """,
                (cr_id, job_id, summary, files_changed, diff_dir, now_iso()),
            )
            self.conn.commit()

        retry_on_locked(_do)

    def get(self, cr_id: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self.conn.execute(
            "SELECT * FROM change_requests WHERE id = ?", (cr_id,)
        ).fetchone()
        return row

    def list(self, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute(
                "SELECT * FROM change_requests WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM change_requests ORDER BY created_at DESC"
        ).fetchall()

    def set_status(self, cr_id: str, status: str, applied: bool = False) -> None:
        if applied:
            self.conn.execute(
                "UPDATE change_requests SET status = ?, applied_at = ? WHERE id = ?",
                (status, now_iso(), cr_id),
            )
        else:
            self.conn.execute(
                "UPDATE change_requests SET status = ? WHERE id = ?", (status, cr_id)
            )
        self.conn.commit()

    def set_files_changed(self, cr_id: str, files_changed: int) -> None:
        self.conn.execute(
            "UPDATE change_requests SET files_changed = ? WHERE id = ?",
            (files_changed, cr_id),
        )
        self.conn.commit()


class AskHistoryRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(
        self,
        question: str,
        answer: str,
        citations: str | None = None,
        change_request_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO ask_history (question, answer, citations, change_request_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (question, answer, citations, change_request_id, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def get(self, history_id: int) -> sqlite3.Row | None:
        return cast(
            "sqlite3.Row | None",
            self.conn.execute(
                "SELECT * FROM ask_history WHERE id = ?", (history_id,)
            ).fetchone(),
        )

    def list(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM ask_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def set_change_request(self, history_id: int, change_request_id: str) -> None:
        self.conn.execute(
            "UPDATE ask_history SET change_request_id = ? WHERE id = ?",
            (change_request_id, history_id),
        )
        self.conn.commit()

    def delete(self, history_id: int) -> None:
        self.conn.execute("DELETE FROM ask_history WHERE id = ?", (history_id,))
        self.conn.commit()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM ask_history")
        self.conn.commit()


def _row_to_source(row: sqlite3.Row) -> Source:
    return Source.model_validate(
        {
            "id": row["id"],
            "path": row["path"],
            "type": row["type"],
            "title": row["title"],
            "hash": row["hash"],
            "added_at": row["added_at"],
            "processed_at": row["processed_at"],
            "status": row["status"],
        }
    )


def _row_to_page(row: sqlite3.Row) -> Page:
    return Page.model_validate(
        {
            "id": row["id"],
            "path": row["path"],
            "title": row["title"],
            "type": row["type"],
            "summary": row["summary"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "last_updated_at": row["last_updated_at"],
            "source_count": row["source_count"],
            "confidence": row["confidence"],
        }
    )
