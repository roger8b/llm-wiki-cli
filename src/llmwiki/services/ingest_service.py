"""Ingest service: orchestrates source -> agent -> change request.

The ``runner`` is injectable for testing (without LLM). In production it uses the DeepAgents agent
(``agents.factory.run_ingestion``), imported lazily.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path

from ..core.config import WorkspaceConfig
from ..core.errors import SourceAlreadyProcessedError
from ..core.misc import sha256
from ..core.models import ChangeRequest, FileChange, SourceStatus
from ..core.paths import BrainPaths
from ..db.repo import JobEventRepo, JobRepo, SourceRepo
from ..llm_agents.backend import ChangeRequestBackend
from ..llm_agents.models import IngestionResult, OutlinePlan
from ..llm_agents.telemetry import ExecutionMeta
from ..sources.extractors import ExtractedSource
from . import change_request_service
from .change_request_service import create_from_changes

logger = logging.getLogger("llmwiki.services.ingest")

# Live-progress event sink: ``emit(kind, payload)`` appends to ``job_events``
# (#272). ``None`` disables eventing (e.g. CLI runs without a job timeline).
EventEmitter = Callable[[str, "dict[str, object] | None"], None]


def _make_event_emitter(
    paths: BrainPaths, job_id: int
) -> tuple[EventEmitter, Callable[[], None]]:
    """Build a thread-safe live-event sink for a job (#272).

    The agent's tool callbacks and the backend's page-write hook may fire from a
    different thread than the service, so the dedicated connection is guarded by
    a lock. Eventing is best-effort — a failure here never breaks the ingest.
    """
    from ..db.connection import get_connection

    conn = get_connection(paths.db_path, apply_schema=False)
    repo = JobEventRepo(conn)
    lock = threading.Lock()

    def emit(kind: str, payload: dict[str, object] | None = None) -> None:
        try:
            with lock:
                repo.append(job_id, kind, payload)
        except Exception:  # noqa: BLE001 — telemetry must never break ingest
            logger.debug("job event emit failed (kind=%s)", kind, exc_info=True)

    def close() -> None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    return emit, close


class _StepTracker:
    """Time each pipeline step and emit start/end timeline events (#272, #273).

    ``step(name)`` closes the previous step (emitting an ``end`` event with its
    ``duration_ms``) and opens a new one, also setting the coarse ``progress``
    label for backward compatibility. ``finish()`` closes the last step. The
    accumulated ``durations`` map (step name -> ms) is persisted into the job
    result so per-step timing is auditable — the foundation for the #276
    baseline. ``pages_staged`` is stamped on each event so the UI sees the
    staging count grow live.
    """

    def __init__(self, emit: EventEmitter | None, job_repo: JobRepo, job_id: int) -> None:
        self.emit: EventEmitter | None = emit
        self._job_repo = job_repo
        self._job_id = job_id
        self._name: str | None = None
        self._start: float | None = None
        self.durations: dict[str, int] = {}
        self.pages_staged = 0

    def _close(self) -> None:
        if self._name is None or self._start is None:
            return
        duration_ms = int((time.perf_counter() - self._start) * 1000)
        # Accumulate (repeated step names like "chunk 1/3" sum together).
        self.durations[self._name] = self.durations.get(self._name, 0) + duration_ms
        if self.emit is not None:
            self.emit(
                "step",
                {
                    "name": self._name,
                    "status": "end",
                    "duration_ms": duration_ms,
                    "pages_staged": self.pages_staged,
                },
            )
        self._name = None
        self._start = None

    def step(self, name: str) -> None:
        self._close()
        self._name = name
        self._start = time.perf_counter()
        self._job_repo.set_progress(self._job_id, name)
        if self.emit is not None:
            self.emit("step", {"name": name, "status": "start", "pages_staged": self.pages_staged})

    def telemetry(self, meta: ExecutionMeta | None, **extra: object) -> None:
        """Emit a per-pass telemetry event from the factory-captured meta."""
        if self.emit is None or meta is None:
            return
        payload: dict[str, object] = {**meta.to_dict(), "pages_staged": self.pages_staged, **extra}
        self.emit("telemetry", payload)

    def finish(self) -> None:
        self._close()

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


def _empty_cr_note(result: IngestionResult, meta: ExecutionMeta | None) -> str:
    """Human-readable reason an ingestion produced no change request (#237 follow-up).

    The agent ran without error but staged nothing. Surface WHY in the job result
    so the UI stops showing a bare, silent "no changes proposed".
    """
    declared = {p.lstrip("/") for p in (*result.new_pages, *result.affected_pages)}
    if declared:
        return (
            f"The agent listed pages ({', '.join(sorted(declared))}) but wrote none — "
            "the model likely did not call the write tools (write_file/edit_file)."
        )
    if meta is not None and meta.used_fallback:
        return (
            "The model returned no structured output and called no write tools — its "
            "tool-calling may be too weak for ingestion; try a stronger model."
        )
    return (
        "The agent found nothing to record (source empty/too short, a duplicate, or "
        "already covered by the wiki)."
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
    fix_findings: list[str] | None = None,
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
        fix_findings=fix_findings,
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


def _concept_key(text: str) -> str:
    """Cheap case/slug-insensitive key for concept→chunk matching (#294)."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized.lower()).split())


def _concept_matches_chunk(concept: str, chunk: str) -> bool:
    concept_key = _concept_key(concept)
    if not concept_key:
        return False
    return f" {concept_key} " in f" {_concept_key(chunk)} "


def _scoped_outlines(outline: OutlinePlan, chunks: list[str]) -> list[OutlinePlan]:
    """Return one outline per chunk, keeping unmatched concepts global (#294)."""
    if not chunks or not outline.concepts:
        return [outline for _ in chunks]
    scoped: list[list[str]] = [[] for _ in chunks]
    for concept in outline.concepts:
        matches = [i for i, chunk in enumerate(chunks) if _concept_matches_chunk(concept, chunk)]
        if not matches:
            matches = list(range(len(chunks)))
        for i in matches:
            scoped[i].append(concept)
    return [outline.model_copy(update={"concepts": concepts}) for concepts in scoped]


def _lint_staging(paths: BrainPaths, staging: dict[str, str]) -> list[str]:
    """Structural lint of the backend staging, as ``"kind: message"`` strings (#166).

    ``known_titles`` = titles on disk + titles in staging, so a wikilink to a
    sibling page created in the same run resolves and is not a broken link.
    Orphan detection does not apply to staging (a new page may be linked later).
    """
    from . import lint_service

    disk_files = {
        paths.relative(f): f.read_text(encoding="utf-8")
        for f in lint_service._iter_wiki_files(paths.wiki)
    }
    known_titles = {
        **lint_service.titles_from_contents(disk_files),
        **lint_service.titles_from_contents(staging),
    }
    findings = lint_service.lint_contents(staging, known_titles=known_titles)
    return [f"{f.kind}: {f.message}" for f in findings]


def _self_correct(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    runner: Runner,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None],
    paths: BrainPaths,
    job_repo: JobRepo,
    job_id: int,
    tracker: _StepTracker | None = None,
) -> list[str]:
    """Lint the staging and let the agent fix structural issues before the CR (#166).

    Returns the findings that remain after up to ``cfg.agent_fix_retries`` fix
    passes (empty when clean). A clean first pass costs zero extra invocations.
    """
    findings = _lint_staging(paths, backend.staging)
    if not findings:
        return findings
    # Deterministic code fixes first: clear trivial findings (missing
    # frontmatter, directory-implied page type) with ZERO LLM invocations (#279).
    # Only the findings code can't settle reach the agent below.
    from . import lint_service

    fixed = lint_service.autofix_contents(backend.staging)
    if fixed:
        for path, content in fixed.items():
            backend.write(path, content)
        logger.info(
            "ingest(%s): code auto-fixed %d page(s) before any fix invoke (#279)",
            source_path,
            len(fixed),
        )
        findings = _lint_staging(paths, backend.staging)
    if not findings or cfg.agent_fix_retries <= 0:
        return findings
    # Keep the pre-fix telemetry (e.g. the multi-pass aggregate) and fold each
    # fix pass into it, so the CR's execution totals stay complete.
    metas: list[ExecutionMeta] = [backend.execution_meta] if backend.execution_meta else []
    attempt = 0
    while findings and attempt < cfg.agent_fix_retries:
        attempt += 1
        logger.info(
            "ingest(%s): structural lint found %d issue(s); fix pass %d/%d",
            source_path,
            len(findings),
            attempt,
            cfg.agent_fix_retries,
        )
        if tracker is not None:
            tracker.step("fixing_structural_issues")
        runner(
            cfg,
            backend,
            source_path=source_path,
            source_text=source_text,
            source_meta=source_meta,
            fix_findings=findings,
        )
        if backend.execution_meta is not None:
            metas.append(backend.execution_meta)
            if tracker is not None:
                tracker.telemetry(backend.execution_meta, phase="fix", attempt=attempt)
        findings = _lint_staging(paths, backend.staging)
    backend.execution_meta = ExecutionMeta.merge(metas)
    if findings:
        logger.warning(
            "ingest(%s): %d structural issue(s) unresolved after %d fix pass(es): %s",
            source_path,
            len(findings),
            attempt,
            findings,
        )
    return findings


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
    tracker: _StepTracker | None = None,
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

    if tracker is not None:
        tracker.step("outlining")
    summaries = [c[:500] for c in chunks]
    outline = outline_runner(cfg, source_meta=source_meta, chunk_summaries=summaries)
    outlines = (
        _scoped_outlines(outline, chunks)
        if cfg.ingest_scope_concepts_per_chunk
        else [outline for _ in chunks]
    )

    metas: list[ExecutionMeta] = []
    concurrency = max(1, cfg.ingest_chunk_concurrency)
    if concurrency == 1 or n == 1:
        # Serial path (#162): the shared backend's staging overlay lets chunk N
        # see pages staged by chunk N-1 — free intra-source dedup.
        results: list[IngestionResult] = []
        for i, chunk in enumerate(chunks):
            if cancel_check is not None and cancel_check():
                raise JobCancelledError("cancelled between chunk passes")
            if tracker is not None:
                tracker.step(f"chunk {i + 1}/{n}")
            result = runner(
                cfg,
                backend,
                source_path=source_path,
                source_text=chunk,
                source_meta=source_meta,
                outline=outlines[i],
                part=(i + 1, n),
            )
            results.append(result)
            if backend.execution_meta is not None:
                metas.append(backend.execution_meta)
                # Per-pass telemetry the instant the chunk finishes (#273) — not
                # only in the merged total below.
                if tracker is not None:
                    tracker.telemetry(backend.execution_meta, phase="chunk", part=i + 1, of=n)

        backend.execution_meta = ExecutionMeta.merge(metas)
        return _merge_results(results)

    # Parallel path (#277): each chunk runs on its OWN isolated backend so the
    # passes don't contend on a single staging dict. Stagings are merged into the
    # shared backend deterministically — the HIGHEST chunk index wins a path
    # collision, mirroring the serial shared-backend semantics where a later
    # chunk's write overwrites an earlier one — so the resulting CR is identical
    # to the serial run and independent of thread scheduling. Cancellation is
    # cooperative: workers probe ``cancel_check`` and the first failure tears the
    # pool down.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if cancel_check is not None and cancel_check():
        raise JobCancelledError("cancelled between chunk passes")
    logger.info(
        "ingest(%s): running %d chunk passes with concurrency %d",
        source_path,
        n,
        concurrency,
    )

    def _run_chunk(
        i: int, chunk: str
    ) -> tuple[int, IngestionResult, dict[str, str], ExecutionMeta | None]:
        if cancel_check is not None and cancel_check():
            raise JobCancelledError("cancelled before chunk pass")
        chunk_backend = ChangeRequestBackend(cfg.brain_root)
        chunk_backend.cancel_check = cancel_check
        chunk_backend.dedup_check = backend.dedup_check
        result = runner(
            cfg,
            chunk_backend,
            source_path=source_path,
            source_text=chunk,
            source_meta=source_meta,
            outline=outlines[i],
            part=(i + 1, n),
        )
        return i, result, dict(chunk_backend.staging), chunk_backend.execution_meta

    indexed: list[tuple[int, IngestionResult]] = []
    staged_from: dict[str, int] = {}  # path -> winning chunk index
    collisions = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_run_chunk, i, c) for i, c in enumerate(chunks)]
        try:
            for fut in as_completed(futures):
                i, result, staging, meta = fut.result()  # re-raises cancellation
                indexed.append((i, result))
                # Merge into the shared backend. New paths are added; on a
                # collision the higher chunk index wins (matches serial overwrite
                # order). The staged count only ever grows, so the live
                # ``pages_staged`` telemetry stays monotonic regardless of which
                # pass finished first.
                for path, content in staging.items():
                    prev = staged_from.get(path)
                    if prev is None:
                        backend.staging[path] = content
                        staged_from[path] = i
                    else:
                        collisions += 1
                        if i > prev:
                            backend.staging[path] = content
                            staged_from[path] = i
                if meta is not None:
                    metas.append(meta)
                if tracker is not None:
                    tracker.pages_staged = len(backend.staging)
                    tracker.step(f"chunk {i + 1}/{n}")
                    tracker.telemetry(meta, phase="chunk", part=i + 1, of=n)
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise

    if collisions:
        logger.info(
            "ingest(%s): %d path collision(s) merged across parallel chunks",
            source_path,
            collisions,
        )
    backend.execution_meta = ExecutionMeta.merge(metas)
    results = [r for _, r in sorted(indexed, key=lambda t: t[0])]
    return _merge_results(results)


def _extract_for_job(
    source_file: Path,
    cfg: WorkspaceConfig,
    job_repo: JobRepo,
    job_id: int,
    tracker: _StepTracker | None = None,
) -> ExtractedSource:
    """Extract a source's text + metadata, reporting progress on the job.

    Audio is transcribed with faster-whisper (#76) using the configured model;
    everything else uses the synchronous extractor registry.
    """
    from ..sources.extractors import extract, source_type

    # Always report the coarse progress label; add the timeline step only when a
    # tracker is present (it is in ``ingest()``; absent when this helper is
    # called directly, e.g. in extraction unit tests).
    def report(step: str) -> None:
        if tracker is not None:
            tracker.step(step)
        else:
            job_repo.set_progress(job_id, step)

    if source_type(source_file) == "audio":
        from ..sources.extractors import audio

        return audio.transcribe(
            source_file,
            model=cfg.whisper_model,
            language=cfg.whisper_language,
            progress=report,
        )
    report("extracting")
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
    # Live-progress event sink (#272): its own connection so the agent's tool
    # callbacks (possibly off-thread) never share the service connection.
    emit, close_events = _make_event_emitter(paths, job_id)
    backend: ChangeRequestBackend | None = None
    tracker = _StepTracker(emit, job_repo, job_id)

    def event_sink(kind: str, payload: dict[str, object] | None = None) -> None:
        # Keep the live staging count current and stamp it on every event (#273).
        if backend is not None:
            tracker.pages_staged = len(backend.staging)
        if isinstance(payload, dict):
            payload.setdefault("pages_staged", tracker.pages_staged)
        emit(kind, payload)

    tracker.emit = event_sink
    try:
        # Extraction runs INSIDE the job: audio transcription (#76) is slow, so
        # progress is reported and a failure is recorded on the job.
        extracted = _extract_for_job(source_file, cfg, job_repo, job_id, tracker)
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
        backend.on_event = event_sink
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
                tracker=tracker,
            )
        else:
            tracker.step("running_agent")
            result = runner(
                cfg, backend, source_path=rel, source_text=text, source_meta=source_meta
            )
            tracker.telemetry(backend.execution_meta, phase="single", part=1, of=1)
        # Self-correction: lint the staging and let the agent fix structural
        # issues before the CR; leftover findings become CR warnings (#166).
        warnings = _self_correct(
            cfg,
            backend,
            runner=runner,
            source_path=rel,
            source_text=text,
            source_meta=source_meta,
            paths=paths,
            job_repo=job_repo,
            job_id=job_id,
            tracker=tracker,
        )
        for warning in warnings:
            event_sink("warning", {"message": warning})
        tracker.step("creating_change_request")
        changes = backend.collect_changes()
        _audit_result(result, changes, rel)
        meta = backend.execution_meta
        execution = meta.to_dict() if meta is not None else None
        # Close the last step so its duration lands before we persist the map,
        # giving both the CR meta.json and the job result a complete per-step
        # timing baseline (#276).
        tracker.finish()
        cr = create_from_changes(
            changes,
            result.summary,
            paths,
            conn,
            job_id=job_id,
            source_path=rel if rel.startswith("raw/") else None,
            execution=execution,
            warnings=warnings,
            durations_ms=tracker.durations,
        )
        result_payload: dict[str, object] = {
            "cr": cr.id,
            "files": cr.files_changed,
            "execution": execution,
            "durations_ms": tracker.durations,
        }
        if not changes:
            # Explain the empty CR so the "no changes" outcome isn't silent.
            note = _empty_cr_note(result, meta)
            result_payload["note"] = note
            event_sink("warning", {"message": note})
        job_repo.complete(job_id, result=json.dumps(result_payload))
        return cr
    except JobCancelledError as exc:
        job_repo.cancel(job_id, result=json.dumps({"cancelled": True, "reason": str(exc)}))
        raise
    except Exception as exc:  # noqa: BLE001
        job_repo.complete(job_id, error=str(exc))
        raise
    finally:
        close_events()


__all__ = ["ingest", "change_request_service"]
