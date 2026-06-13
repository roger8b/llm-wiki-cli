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
from ..llm_agents.models import IngestionResult, OutlinePlan
from ..llm_agents.telemetry import ExecutionMeta
from ..sources.extractors import ExtractedSource
from . import change_request_service
from .change_request_service import create_from_changes

logger = logging.getLogger("llmwiki.services.ingest")

# runner(cfg, backend, *, source_path, source_text, source_meta[, outline, part])
#   -> IngestionResult
# ``source_meta`` carries optional provenance (title/author/date/url) — #163.
# ``outline``/``part`` are only passed on multi-pass chunk runs — #162.
Runner = Callable[..., IngestionResult]
# outline_runner(cfg, *, source_meta, chunk_summaries) -> OutlinePlan (#162)
OutlineRunner = Callable[..., OutlinePlan]


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


def _make_dedup_check(
    paths: BrainPaths,
) -> Callable[[str], list[tuple[str, str, str]]]:
    """Build the duplicate guardrail for the backend (#167).

    Uses its own short-lived connection (the agent runs off-thread, where the
    service's connection is not safe to share).
    """
    from ..core.dedup import find_similar_pages
    from ..db.connection import get_connection

    def check(title: str) -> list[tuple[str, str, str]]:
        conn = get_connection(paths.db_path)
        try:
            return find_similar_pages(title, conn)
        finally:
            conn.close()

    return check


def _default_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
    outline: OutlinePlan | None = None,
    part: tuple[int, int] | None = None,
) -> IngestionResult:
    from ..llm_agents.factory import run_ingestion

    return run_ingestion(
        cfg,
        backend,
        source_path=source_path,
        source_text=source_text,
        source_meta=source_meta,
        outline=outline,
        part=part,
    )


def _default_outline_runner(
    cfg: WorkspaceConfig,
    *,
    source_meta: dict[str, str | None] | None = None,
    chunk_summaries: list[str],
) -> OutlinePlan:
    from ..llm_agents.factory import run_outline

    return run_outline(cfg, source_meta=source_meta, chunk_summaries=chunk_summaries)


def _merge_results(results: list[IngestionResult]) -> IngestionResult:
    """Fold per-pass ingestion results into one aggregate (#162).

    Unions declared pages (so ``_audit_result`` checks the whole source) and
    joins the per-pass summaries.
    """
    if len(results) == 1:
        return results[0]
    new_pages: list[str] = []
    affected: list[str] = []
    summaries: list[str] = []
    for r in results:
        new_pages.extend(r.new_pages)
        affected.extend(r.affected_pages)
        if r.summary:
            summaries.append(r.summary)
    return IngestionResult(
        summary=" ".join(summaries),
        new_pages=sorted(dict.fromkeys(new_pages)),
        affected_pages=sorted(dict.fromkeys(affected)),
    )


def _run_passes(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    runner: Runner,
    outline_runner: OutlineRunner,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None],
    job_repo: JobRepo,
    job_id: int,
    cancel_check: Callable[[], bool] | None,
) -> IngestionResult:
    """Multi-pass ingestion of a long source over a SINGLE shared backend (#162).

    Outline first, then one ``runner`` invocation per chunk. The shared backend's
    staging overlay lets chunk N see pages staged by chunk N-1 — free intra-source
    dedup. Cancellation is checked between passes; telemetry is summed.
    """
    from ..core.errors import JobCancelledError
    from ..sources.chunking import chunk_text

    chunks = chunk_text(
        source_text,
        size=cfg.chunk_size_chars,
        overlap=cfg.chunk_overlap_chars,
    )
    n = len(chunks)
    logger.info("ingest(%s): long source -> %d chunks", source_path, n)

    job_repo.set_progress(job_id, "outlining")
    summaries = [c[:500] for c in chunks]
    outline = outline_runner(cfg, source_meta=source_meta, chunk_summaries=summaries)

    metas: list[ExecutionMeta] = []
    results: list[IngestionResult] = []
    for i, chunk in enumerate(chunks):
        if cancel_check is not None and cancel_check():
            raise JobCancelledError("cancelled between chunk passes")
        job_repo.set_progress(job_id, f"chunk {i + 1}/{n}")
        result = runner(
            cfg,
            backend,
            source_path=source_path,
            source_text=chunk,
            source_meta=source_meta,
            outline=outline,
            part=(i + 1, n),
        )
        results.append(result)
        if backend.execution_meta is not None:
            metas.append(backend.execution_meta)

    backend.execution_meta = ExecutionMeta.merge(metas)
    return _merge_results(results)


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
    outline_runner: OutlineRunner | None = None,
    job_id: int | None = None,
    force: bool = False,
    cancel_check: Callable[[], bool] | None = None,
) -> ChangeRequest:
    """Reads a source, runs the ingestion agent, and creates a change request.

    Raises ``SourceAlreadyProcessedError`` (before any LLM call) when the source
    content was already ingested and applied, unless ``force`` is set.
    ``cancel_check`` is polled by the agent to abort cooperatively. Sources
    longer than ``cfg.chunk_threshold_chars`` go through the multi-pass flow
    (#162); everything else uses the single-pass path unchanged.
    """
    from ..core.errors import JobCancelledError

    runner = runner or _default_runner
    outline_runner = outline_runner or _default_outline_runner
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
        backend = ChangeRequestBackend(paths.root)
        backend.cancel_check = cancel_check
        backend.dedup_check = _make_dedup_check(paths)
        if len(text) > cfg.chunk_threshold_chars:
            result = _run_passes(
                cfg,
                backend,
                runner=runner,
                outline_runner=outline_runner,
                source_path=rel,
                source_text=text,
                source_meta=source_meta,
                job_repo=job_repo,
                job_id=job_id,
                cancel_check=cancel_check,
            )
        else:
            job_repo.set_progress(job_id, "running_agent")
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
