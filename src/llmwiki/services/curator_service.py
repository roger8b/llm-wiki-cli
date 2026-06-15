"""Scheduled/manual curator: orchestrates lint → verified fixes → auto-link (#41).

A thin orchestration layer over the heavy lifting that already lives in its own
stories: batched lint (#173), verified maintenance (#174) and deterministic
auto-link (#44). It NEVER applies anything — every change is proposed as a
``pending_review`` change request. Persists ``last_curation_at`` so the backend
scheduler knows when to run next.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from ..core.config import WorkspaceConfig
from ..core.misc import now_iso
from ..core.models import CurationReport, LintFinding
from ..core.paths import BrainPaths
from ..db.repo import MetaRepo
from . import autolink_service, change_request_service, lint_service, maintenance_service

LAST_CURATION_KEY = "last_curation_at"

Progress = Callable[[str], None]


def get_last_curation(conn: sqlite3.Connection) -> str | None:
    return MetaRepo(conn).get(LAST_CURATION_KEY)


def run_curation(
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    progress: Progress | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> CurationReport:
    """Run lint → verified fixes → auto-link, proposing CRs (never applying)."""

    def _step(label: str) -> None:
        if progress is not None:
            progress(label)

    crs: list[str] = []
    tokens_in = 0
    tokens_out = 0

    # Step 1: lint (batched + budget-aware when semantic).
    _step("lint")
    if cfg.curation_semantic:
        findings = lint_service.lint_batched(paths, cfg).findings
    else:
        findings = lint_service.lint_structural(paths)

    # Step 2: drop findings already covered by a pending CR (no duplicates).
    _step("dedup")
    findings = lint_service.annotate_with_pending_crs(findings, conn)
    pending: list[LintFinding] = [f for f in findings if f.related_cr is not None]
    to_fix: list[LintFinding] = [f for f in findings if f.related_cr is None]

    # Step 3: verified maintenance over the remaining findings → CR(s).
    _step("fix")
    unresolved = 0
    if to_fix and not (cancel_check is not None and cancel_check()):
        cr = maintenance_service.maintain(
            to_fix, paths, conn, cfg, cancel_check=cancel_check
        )
        if cr is not None:
            crs.append(cr.id)
            full = change_request_service.get(cr.id, conn)
            if full is not None:
                unresolved = sum(
                    1 for w in (full.warnings or []) if w.startswith("unresolved:")
                )
                tokens_in, tokens_out = _exec_tokens(full.execution, tokens_in, tokens_out)

    # Step 4: deterministic auto-link across the wiki (proposes a CR).
    _step("autolink")
    autolink_mentions = 0
    if not (cancel_check is not None and cancel_check()):
        result = autolink_service.propose_autolinks(paths, conn, dry_run=False)
        if isinstance(result, dict):
            autolink_mentions = len(result.get("mentions", []))  # type: ignore[arg-type]
        else:
            crs.append(result.id)
            # propose_autolinks reports mentions only on dry-run; count CR files.
            autolink_mentions = result.files_changed

    ran_at = now_iso()
    MetaRepo(conn).set(LAST_CURATION_KEY, ran_at)

    resolved = len(to_fix) - unresolved if to_fix else 0
    return CurationReport(
        findings_total=len(findings),
        findings_already_covered=len(pending),
        resolved=max(0, resolved),
        unresolved=unresolved,
        change_requests=crs,
        autolink_mentions=autolink_mentions,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        ran_at=ran_at,
    )


def _exec_tokens(
    execution: dict[str, Any] | None, tin: int, tout: int
) -> tuple[int, int]:
    if not execution:
        return tin, tout
    try:
        tin += int(execution.get("tokens_in", 0) or 0)
        tout += int(execution.get("tokens_out", 0) or 0)
    except (TypeError, ValueError):
        pass
    return tin, tout
