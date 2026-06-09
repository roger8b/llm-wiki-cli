"""Ingest service: orchestrates source -> agent -> change request.

The ``runner`` is injectable for testing (without LLM). In production it uses the DeepAgents agent
(``agents.factory.run_ingestion``), imported lazily.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ..agents.backend import ChangeRequestBackend
from ..agents.models import IngestionResult
from ..core.config import WorkspaceConfig
from ..core.errors import SourceAlreadyProcessedError
from ..core.misc import sha256
from ..core.models import ChangeRequest, FileChange, SourceStatus
from ..core.paths import BrainPaths
from ..db.repo import JobRepo, SourceRepo
from . import change_request_service
from .change_request_service import create_from_changes

logger = logging.getLogger("llmwiki.services.ingest")

# runner(cfg, backend, *, source_path, source_text) -> IngestionResult
Runner = Callable[..., IngestionResult]


def _check_already_processed(source_file: Path, conn: sqlite3.Connection) -> None:
    """Raise ``SourceAlreadyProcessedError`` if this content was already applied.

    Dedup is by content hash (same digest scheme as the source manager), so a
    renamed copy of already-ingested content is still skipped. Only sources in
    the ``processed`` state count — a pending source whose CR was never applied
    can be re-ingested freely.
    """
    digest = sha256(source_file.read_bytes())
    existing = SourceRepo(conn).get_by_hash(digest)
    if existing is not None and existing.status == SourceStatus.processed:
        raise SourceAlreadyProcessedError(
            f"Source already processed (hash {digest[:12]}…): {existing.path}. "
            "Use force=True to re-ingest."
        )


def _audit_result(
    result: IngestionResult, changes: list[FileChange], source_path: str
) -> None:
    """Cross-check what the LLM *declared* against what it actually wrote.

    Catches phantom change requests (summary full of promises, nothing staged)
    and silent mismatches, surfacing them as warnings for observability.
    """
    declared = {p.lstrip("/") for p in (*result.new_pages, *result.affected_pages)}
    actual = {c.path for c in changes}
    if declared and not changes:
        logger.warning(
            "ingest(%s): phantom result — LLM declared %s but wrote nothing.",
            source_path,
            sorted(declared),
        )
        return
    missing = declared - actual
    extra = actual - declared
    if missing:
        logger.warning(
            "ingest(%s): LLM declared pages it did not write: %s",
            source_path,
            sorted(missing),
        )
    if extra:
        logger.warning(
            "ingest(%s): LLM wrote pages it did not declare: %s",
            source_path,
            sorted(extra),
        )


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
    job_id: int | None = None,
    force: bool = False,
) -> ChangeRequest:
    """Reads a source, runs the ingestion agent, and creates a change request.

    Raises ``SourceAlreadyProcessedError`` (before any LLM call) when the source
    content was already ingested and applied, unless ``force`` is set.
    """
    from ..sources.extractors import extract_text

    runner = runner or _default_runner
    inside_brain = paths.root in source_file.resolve().parents
    rel = paths.relative(source_file) if inside_brain else str(source_file)

    # Dedup before spending an LLM call (and before any job is created).
    if not force:
        _check_already_processed(source_file, conn)

    text = extract_text(source_file)

    job_repo = JobRepo(conn)
    if job_id is None:
        job_id = job_repo.create("ingest", json.dumps({"source": rel}), status="running")
    try:
        backend = ChangeRequestBackend(paths.root)
        result = runner(cfg, backend, source_path=rel, source_text=text)
        changes = backend.collect_changes()
        _audit_result(result, changes, rel)
        meta = backend.execution_meta
        execution = meta.to_dict() if meta is not None else None
        cr = create_from_changes(
            changes,
            result.summary,
            paths,
            conn,
            job_id=job_id,
            source_path=rel if rel.startswith("raw/") else None,
            execution=execution,
        )
        job_repo.complete(
            job_id,
            result=json.dumps(
                {"cr": cr.id, "files": cr.files_changed, "execution": execution}
            ),
        )
        return cr
    except Exception as exc:  # noqa: BLE001
        job_repo.complete(job_id, error=str(exc))
        raise


__all__ = ["ingest", "change_request_service"]
