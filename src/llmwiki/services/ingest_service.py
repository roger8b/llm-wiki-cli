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

from ..core.config import WorkspaceConfig
from ..core.errors import SourceAlreadyProcessedError
from ..core.misc import sha256
from ..core.models import ChangeRequest, FileChange, SourceStatus
from ..core.paths import BrainPaths
from ..db.repo import JobRepo, SourceRepo
from ..llm_agents.backend import ChangeRequestBackend
from ..llm_agents.models import IngestionResult
from ..sources.extractors import ExtractedSource
from . import change_request_service
from .change_request_service import create_from_changes

logger = logging.getLogger("llmwiki.services.ingest")

# runner(cfg, backend, *, source_path, source_text, source_meta) -> IngestionResult
# ``source_meta`` carries optional provenance (title/author/date/url) — #163.
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
    source_meta: dict[str, str | None] | None = None,
) -> IngestionResult:
    from ..llm_agents.factory import run_ingestion

    return run_ingestion(
        cfg,
        backend,
        source_path=source_path,
        source_text=source_text,
        source_meta=source_meta,
    )


def _extract_for_job(
    source_file: Path, cfg: WorkspaceConfig, job_repo: JobRepo, job_id: int
) -> ExtractedSource:
    """Extract a source's text + metadata, reporting progress on the job.

    Audio is transcribed with faster-whisper (#76) using the configured model;
    everything else uses the synchronous extractor registry.
    """
    from ..sources.extractors import extract, source_type

    if source_type(source_file) == "audio":
        from ..sources.extractors import audio

        return audio.transcribe(
            source_file,
            model=cfg.whisper_model,
            language=cfg.whisper_language,
            progress=lambda step: job_repo.set_progress(job_id, step),
        )
    job_repo.set_progress(job_id, "extracting")
    return extract(source_file)


def ingest(
    source_file: Path,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    runner: Runner | None = None,
    job_id: int | None = None,
    force: bool = False,
    cancel_check: Callable[[], bool] | None = None,
) -> ChangeRequest:
    """Reads a source, runs the ingestion agent, and creates a change request.

    Raises ``SourceAlreadyProcessedError`` (before any LLM call) when the source
    content was already ingested and applied, unless ``force`` is set.
    ``cancel_check`` is polled by the agent to abort cooperatively.
    """
    from ..core.errors import JobCancelledError

    runner = runner or _default_runner
    inside_brain = paths.root in source_file.resolve().parents
    rel = paths.relative(source_file) if inside_brain else str(source_file)

    # Dedup before spending an LLM call (and before any job is created).
    if not force:
        _check_already_processed(source_file, conn)

    job_repo = JobRepo(conn)
    if job_id is None:
        job_id = job_repo.create("ingest", json.dumps({"source": rel}), status="running")
    try:
        # Extraction runs INSIDE the job: audio transcription (#76) is slow, so
        # progress is reported and a failure is recorded on the job.
        extracted = _extract_for_job(source_file, cfg, job_repo, job_id)
        text = extracted.text
        source_meta: dict[str, str | None] = {
            "title": extracted.title,
            "author": extracted.author,
            "date": extracted.date,
            "url": extracted.url,
        }
        job_repo.set_progress(job_id, "running_agent")
        backend = ChangeRequestBackend(paths.root)
        backend.cancel_check = cancel_check
        result = runner(
            cfg, backend, source_path=rel, source_text=text, source_meta=source_meta
        )
        job_repo.set_progress(job_id, "creating_change_request")
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
    except JobCancelledError as exc:
        job_repo.cancel(job_id, result=json.dumps({"cancelled": True, "reason": str(exc)}))
        raise
    except Exception as exc:  # noqa: BLE001
        job_repo.complete(job_id, error=str(exc))
        raise


__all__ = ["ingest", "change_request_service"]
