"""Ingest service: orquestra fonte → agente → change request.

O ``runner`` é injetável para teste (sem LLM). Em produção usa o agente DeepAgents
(``agents.factory.run_ingestion``), importado preguiçosamente.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ..agents.backend import ChangeRequestBackend
from ..agents.models import IngestionResult
from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest
from ..core.paths import BrainPaths
from ..db.repo import JobRepo
from . import change_request_service
from .change_request_service import create_from_changes

# runner(cfg, backend, *, source_path, source_text) -> IngestionResult
Runner = Callable[..., IngestionResult]


def _default_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
) -> IngestionResult:
    from ..agents.factory import run_ingestion

    return run_ingestion(cfg, backend, source_path=source_path, source_text=source_text)


def ingest(
    source_file: Path,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    runner: Runner | None = None,
) -> ChangeRequest:
    """Lê uma fonte, roda o agente de ingestão e cria um change request."""
    from ..sources.extractors import extract_text

    runner = runner or _default_runner
    inside_brain = paths.root in source_file.resolve().parents
    rel = paths.relative(source_file) if inside_brain else str(source_file)
    text = extract_text(source_file)

    job_repo = JobRepo(conn)
    job_id = job_repo.create("ingest", json.dumps({"source": rel}))
    try:
        backend = ChangeRequestBackend(paths.root)
        result = runner(cfg, backend, source_path=rel, source_text=text)
        changes = backend.collect_changes()
        cr = create_from_changes(
            changes,
            result.summary,
            paths,
            conn,
            job_id=job_id,
            source_path=rel if rel.startswith("raw/") else None,
        )
        job_repo.complete(job_id, result=json.dumps({"cr": cr.id, "files": cr.files_changed}))
        return cr
    except Exception as exc:  # noqa: BLE001
        job_repo.complete(job_id, error=str(exc))
        raise


__all__ = ["ingest", "change_request_service"]
