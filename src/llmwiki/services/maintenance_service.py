"""Maintenance service: transforms lint findings into a corrective change request."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest, LintFinding
from ..core.paths import BrainPaths
from ..llm_agents.backend import ChangeRequestBackend
from ..llm_agents.models import MaintenanceResult
from . import lint_service
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


def _verify(
    paths: BrainPaths, backend: ChangeRequestBackend, findings: list[LintFinding]
) -> dict[str, str]:
    files = lint_service.disk_staging_files(paths, backend.staging)
    touched = set(backend.staging)
    return lint_service.verify_findings(findings, files, touched=touched)


def maintain(
    findings: list[LintFinding],
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    runner: Runner | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ChangeRequest | None:
    """Runs the maintenance agent, verifies the proposed fixes against the
    findings (re-inviting the agent for unresolved ones up to
    ``agent_fix_retries``), and creates a CR whose persisted verdict reflects
    the verification — not the agent's self-declared ``fixed`` list (#174)."""
    if not findings:
        return None
    runner = runner or _default_runner
    backend = ChangeRequestBackend(paths.root)
    backend.cancel_check = cancel_check

    result = runner(cfg, backend, findings_text=_format_findings(findings))
    verdicts = _verify(paths, backend, findings)

    attempts = 0
    while attempts < max(0, cfg.agent_fix_retries):
        unresolved = [f for f in findings if verdicts[lint_service.finding_id(f)] == "unresolved"]
        if not unresolved:
            break
        if cancel_check is not None and cancel_check():
            break
        result = runner(cfg, backend, findings_text=_format_findings(unresolved))
        verdicts = _verify(paths, backend, findings)
        attempts += 1

    changes = backend.collect_changes()
    if not changes:
        return None

    unresolved_w: list[str] = []
    unverifiable_w: list[str] = []
    for f in findings:
        verdict = verdicts[lint_service.finding_id(f)]
        label = f"{f.kind} — {', '.join(f.pages)}"
        if verdict == "unresolved":
            unresolved_w.append(f"unresolved: {label}")
        elif verdict == "unverifiable":
            unverifiable_w.append(f"unverifiable: {label}")
    warnings = unresolved_w + unverifiable_w

    meta = backend.execution_meta
    return create_from_changes(
        changes,
        result.summary,
        paths,
        conn,
        execution=meta.to_dict() if meta is not None else None,
        warnings=warnings or None,
    )
