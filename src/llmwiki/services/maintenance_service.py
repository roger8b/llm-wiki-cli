"""Maintenance service: transforma achados de lint em um change request de correção."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ..agents.backend import ChangeRequestBackend
from ..agents.models import MaintenanceResult
from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest, LintFinding
from ..core.paths import BrainPaths
from .change_request_service import create_from_changes

# runner(cfg, backend, *, findings_text) -> MaintenanceResult
Runner = Callable[..., MaintenanceResult]


def _default_runner(
    cfg: WorkspaceConfig, backend: ChangeRequestBackend, *, findings_text: str
) -> MaintenanceResult:
    from ..agents.factory import run_maintenance

    return run_maintenance(cfg, backend, findings_text=findings_text)


def _format_findings(findings: list[LintFinding]) -> str:
    return "\n".join(
        f"- [{f.severity.value}] {f.kind}: {f.message} (páginas: {', '.join(f.pages)})"
        for f in findings
    )


def maintain(
    findings: list[LintFinding],
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    runner: Runner | None = None,
) -> ChangeRequest | None:
    """Roda o agente de manutenção sobre os achados e cria um CR (ou None se nada mudar)."""
    if not findings:
        return None
    runner = runner or _default_runner
    backend = ChangeRequestBackend(paths.root)
    result = runner(cfg, backend, findings_text=_format_findings(findings))
    changes = backend.collect_changes()
    if not changes:
        return None
    return create_from_changes(changes, result.summary, paths, conn)
