"""Query service: answers questions using the wiki as the primary source.

Read-only operation. If ``save=True`` and the agent suggests a page, it is
transformed into a change request (never written directly).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

from ..agents.backend import ChangeRequestBackend
from ..agents.models import QueryResult
from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest
from ..core.paths import BrainPaths
from .change_request_service import create_from_changes

logger = logging.getLogger("llmwiki.services.query")

# runner(cfg, backend, *, question, save) -> QueryResult
Runner = Callable[..., QueryResult]


def _default_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None,
    *,
    question: str,
    save: bool,
) -> QueryResult:
    from ..agents.factory import run_query

    return run_query(cfg, backend, question=question, save=save)


def ask(
    question: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    save: bool = False,
    runner: Runner | None = None,
) -> tuple[QueryResult, ChangeRequest | None]:
    """Answers the question. If ``save`` and there is a suggested page, creates a CR."""
    runner = runner or _default_runner
    # Backend always present: scopes read_file to brain root. ``ask`` is a
    # read-only operation, so the backend rejects writes and records any
    # attempt in ``write_attempts`` (audited below) instead of silently
    # dropping them.
    read_backend = ChangeRequestBackend(paths.root, read_only=True)
    result = runner(cfg, read_backend, question=question, save=save)
    if read_backend.write_attempts:
        logger.warning(
            "ask(): agent attempted %d write(s) during a read-only query: %s",
            len(read_backend.write_attempts),
            ", ".join(sorted(set(read_backend.write_attempts))),
        )

    cr: ChangeRequest | None = None
    if save and result.suggested_page is not None:
        backend = ChangeRequestBackend(paths.root)
        backend.write(result.suggested_page.path, result.suggested_page.content)
        changes = backend.collect_changes()
        if changes:
            cr = create_from_changes(
                changes,
                f"Saved answer: {question[:60]}",
                paths,
                conn,
            )
    return result, cr


def promote_answer(
    question: str,
    answer: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    title: str | None = None,
) -> ChangeRequest | None:
    """Turn an already-generated answer into a wiki-page change request.

    No LLM call — the answer markdown is wrapped in a synthesis page and proposed
    as a change request (never written directly), mirroring the ``save`` flow.
    """
    from ..core.markdown import slugify
    from ..core.misc import today

    page_title = (title or question).strip() or "Untitled"
    slug = slugify(page_title)
    path = f"wiki/synthesis/{slug}.md"
    content = (
        "---\n"
        f"title: {page_title}\n"
        "type: synthesis\n"
        "tags: []\n"
        "sources: []\n"
        f"updated_at: {today()}\n"
        "confidence: medium\n"
        "---\n"
        f"# {page_title}\n\n"
        f"{answer.strip()}\n"
    )

    backend = ChangeRequestBackend(paths.root)
    backend.write(path, content)
    changes = backend.collect_changes()
    if not changes:
        return None
    return create_from_changes(
        changes,
        f"Promoted answer: {question[:60]}",
        paths,
        conn,
    )
