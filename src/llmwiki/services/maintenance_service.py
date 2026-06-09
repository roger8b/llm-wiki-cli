"""Maintenance service: transforms lint findings into a corrective change request."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest, LintFinding
from ..core.paths import BrainPaths
from ..llm_agents.backend import ChangeRequestBackend
from ..llm_agents.models import MaintenanceResult
from .change_request_service import create_from_changes

# runner(cfg, backend, *, findings_text) -> MaintenanceResult
Runner = Callable[..., MaintenanceResult]


def _default_runner(
    cfg: WorkspaceConfig, backend: ChangeRequestBackend, *, findings_text: str
) -> MaintenanceResult:
    from ..llm_agents.factory import run_maintenance

    return run_maintenance(cfg, backend, findings_text=findings_text)


def _format_findings(findings: list[LintFinding]) -> str:
    return "\n".join(
        f"- [{f.severity.value}] {f.kind}: {f.message} (pages: {', '.join(f.pages)})"
        for f in findings
    )


def maintain(
    findings: list[LintFinding],
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    runner: Runner | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ChangeRequest | None:
    """Runs the maintenance agent on the findings and creates a CR (or None if nothing changes)."""
    if not findings:
        return None
    runner = runner or _default_runner
    backend = ChangeRequestBackend(paths.root)
    backend.cancel_check = cancel_check
    result = runner(cfg, backend, findings_text=_format_findings(findings))
    changes = backend.collect_changes()
    if not changes:
        return None
    meta = backend.execution_meta
    return create_from_changes(
        changes,
        result.summary,
        paths,
        conn,
        execution=meta.to_dict() if meta is not None else None,
    )
