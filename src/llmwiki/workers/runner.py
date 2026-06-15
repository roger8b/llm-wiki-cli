import json
import logging
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..core.config import load_config
from ..core.errors import JobCancelledError, SourceAlreadyProcessedError
from ..core.paths import BrainPaths, load_active_brain, resolve_input
from ..db.connection import get_connection, retry_on_locked
from ..db.repo import AskHistoryRepo, JobRepo
from ..services import (
    curator_service,
    ingest_service,
    lint_service,
    maintenance_service,
    query_service,
)

logger = logging.getLogger("llmwiki.workers")

# Job types that write change requests / brain state. With worker_concurrency > 1
# (read/write split, ADR 001) these run serialized — never two at once — while
# read-mostly jobs (ask/lint) run concurrently, so a question answers during a
# long ingestion instead of waiting behind it.
_WRITE_TYPES = {"ingest", "maintain", "curate"}


class JobWorker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="LLMWikiJobWorker", daemon=True)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Per-job execution (shared by the single-thread and concurrent paths)
    # ------------------------------------------------------------------
    def _run_job(
        self,
        conn: sqlite3.Connection,
        paths: BrainPaths,
        job_id: int,
        job_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute one already-marked-running job on the given connection.

        Identical behaviour regardless of the dispatch mode; in the concurrent
        path ``conn`` is a per-thread connection so jobs never share one.
        """
        logger.info(f"Processing job {job_id} of type '{job_type}'")
        cfg = load_config(paths)
        result_data: dict[str, Any] | None = None

        # Cooperative-cancellation probe for the agent: reads the
        # cancel_requested flag for THIS job (set by API/CLI on another
        # connection; WAL makes the committed flag visible).
        def _cancelled(c: sqlite3.Connection = conn, jid: int = job_id) -> bool:
            return JobRepo(c).is_cancel_requested(jid)

        try:
            if job_type == "ingest":
                source_path = payload.get("source")
                if not source_path:
                    raise ValueError("Missing 'source' path in ingest payload")
                target = resolve_input(source_path, paths.root)
                force = payload.get("force", False)
                # Run ingest service. It handles its own job completion using job_id.
                try:
                    ingest_service.ingest(
                        target, paths, conn, cfg, job_id=job_id,
                        force=force, cancel_check=_cancelled,
                    )
                except SourceAlreadyProcessedError as exc:
                    # Not an error: the content was already applied.
                    JobRepo(conn).complete(
                        job_id,
                        result=json.dumps({"skipped": True, "reason": str(exc)}),
                    )

            elif job_type == "maintain":
                semantic = payload.get("semantic", False)
                if semantic:
                    findings = lint_service.lint_all(paths, cfg, semantic=True)
                else:
                    findings = lint_service.lint_structural(paths)

                JobRepo(conn).set_progress(job_id, "running_agent")
                cr = maintenance_service.maintain(
                    findings, paths, conn, cfg, cancel_check=_cancelled
                )
                result_data = {
                    "change_request_id": cr.id if cr else None,
                    "files_changed": cr.files_changed if cr else 0,
                    "findings": len(findings),
                }
                JobRepo(conn).complete(job_id, result=json.dumps(result_data))

            elif job_type == "lint":
                semantic = payload.get("semantic", False)
                if semantic:
                    findings = lint_service.lint_all(paths, cfg, semantic=True)
                else:
                    findings = lint_service.lint_structural(paths)

                # Annotate findings already covered by a pending CR.
                findings = lint_service.annotate_with_pending_crs(findings, conn)
                findings_json: list[dict[str, Any]] = [
                    f.model_dump(mode="json") for f in findings
                ]
                result_data = {
                    "findings": findings_json
                }
                JobRepo(conn).complete(job_id, result=json.dumps(result_data))

            elif job_type == "ask":
                question = payload.get("question")
                if not question:
                    raise ValueError("Missing 'question' in ask payload")
                save = payload.get("save", False)
                # Follow-up conversations (#190): an absent id starts a
                # new conversation; prior turns become message context.
                conversation_id = payload.get("conversation_id") or str(uuid.uuid4())
                history = AskHistoryRepo(conn).recent_turns(
                    conversation_id, limit=cfg.ask_history_turns
                )
                JobRepo(conn).set_progress(job_id, "running_agent")
                # Stream answer tokens to jobs.stream_text; the SSE
                # endpoint turns growth into `token` events (#191).
                from ..llm_agents.streaming import TokenBuffer

                def _flush_stream(
                    text: str, c: sqlite3.Connection = conn, j: int = job_id
                ) -> None:
                    JobRepo(c).set_stream(j, text)

                token_buf = TokenBuffer(_flush_stream)
                res, cr = query_service.ask(
                    question,
                    paths,
                    conn,
                    cfg,
                    save=save,
                    cancel_check=_cancelled,
                    history_turns=history,
                    on_token=token_buf.add,
                )
                token_buf.flush()

                result_data = res.model_dump(mode="json")
                result_data["change_request_id"] = cr.id if cr else None
                result_data["conversation_id"] = conversation_id

                # Persist to permanent ask history (per-brain).
                history_id = AskHistoryRepo(conn).insert(
                    question=question,
                    answer=res.answer,
                    citations=json.dumps(
                        [c.model_dump(mode="json") for c in res.citations]
                    ),
                    change_request_id=cr.id if cr else None,
                    conversation_id=conversation_id,
                )
                result_data["history_id"] = history_id
                JobRepo(conn).complete(job_id, result=json.dumps(result_data))

            elif job_type == "curate":
                report = curator_service.run_curation(
                    paths,
                    conn,
                    cfg,
                    progress=lambda step: JobRepo(conn).set_progress(job_id, step),
                    cancel_check=_cancelled,
                )
                JobRepo(conn).complete(
                    job_id, result=json.dumps(report.model_dump(mode="json"))
                )

            else:
                raise ValueError(f"Unknown job type: {job_type}")

            logger.info(f"Job {job_id} completed successfully")

        except JobCancelledError:
            logger.info(f"Job {job_id} cancelled by user")
            # ingest_service self-cancels; for worker-owned jobs
            # (ask/maintain) mark the terminal state here if needed.
            try:
                row = JobRepo(conn).get(job_id)
                if row is None or row["status"] not in ("cancelled", "done", "error"):
                    JobRepo(conn).cancel(
                        job_id, result=json.dumps({"cancelled": True})
                    )
            except Exception:
                logger.exception(f"Failed to mark job {job_id} cancelled")

        except Exception as exc:
            logger.exception(f"Error processing job {job_id}")
            # In case the service raised but didn't complete:
            try:
                JobRepo(conn).complete(job_id, error=str(exc))
            except Exception:
                logger.exception(f"Failed to mark job {job_id} as failed in DB")

    def _run_job_threaded(
        self, paths: BrainPaths, job_id: int, job_type: str, payload: dict[str, Any]
    ) -> None:
        """Concurrent-path entry point: each job gets its own connection."""
        conn = get_connection(paths.db_path, apply_schema=False)
        try:
            self._run_job(conn, paths, job_id, job_type, payload)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _mark_running(conn: sqlite3.Connection, job_id: int) -> None:
        def _do() -> None:
            conn.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
            conn.commit()

        retry_on_locked(_do)

    # ------------------------------------------------------------------
    # Dispatch loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        from ..core.logging import configure_logging

        configure_logging()
        logger.info("Background job worker started.")
        # Hold a single long-lived connection per brain instead of reopening one
        # every poll. Constant connection churn re-runs the WAL pragmas and lets
        # each close attempt a checkpoint, which used to collide with a
        # concurrent CLI writer and surface as "database is locked".
        conn: sqlite3.Connection | None = None
        conn_db_path: Path | None = None
        executor: ThreadPoolExecutor | None = None
        futures: dict[int, tuple[Future[None], bool]] = {}
        try:
            while not self._stop_event.is_set():
                try:
                    # 1. Load active brain
                    try:
                        paths = load_active_brain()
                    except Exception:
                        # No active brain registered yet, wait and try again
                        time.sleep(2)
                        continue

                    # 2. (Re)open the connection only when the active brain
                    #    changes; apply the schema once for that DB.
                    if conn is None or conn_db_path != paths.db_path:
                        if conn is not None:
                            try:
                                conn.close()
                            except Exception:
                                pass
                        conn = get_connection(paths.db_path, apply_schema=True)
                        conn_db_path = paths.db_path

                    concurrency = max(1, load_config(paths).worker_concurrency)
                    if concurrency <= 1:
                        self._poll_serial(conn, paths)
                    else:
                        executor = self._ensure_executor(executor, concurrency)
                        self._poll_concurrent(conn, paths, executor, futures, concurrency)

                except Exception:
                    logger.exception("Error in job worker loop")
                    # Drop the possibly-broken connection so the next iteration
                    # reopens a clean one.
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None
                        conn_db_path = None
                    time.sleep(2)
        finally:
            if executor is not None:
                executor.shutdown(wait=False)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _poll_serial(self, conn: sqlite3.Connection, paths: BrainPaths) -> None:
        """Single-threaded path (worker_concurrency=1): one job at a time."""
        row = conn.execute(
            "SELECT id, type, payload FROM jobs "
            "WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            time.sleep(1)
            return
        job_id = row["id"]
        payload = json.loads(row["payload"]) if row["payload"] else {}
        self._mark_running(conn, job_id)
        self._run_job(conn, paths, job_id, row["type"], payload)

    @staticmethod
    def _ensure_executor(
        executor: ThreadPoolExecutor | None, concurrency: int
    ) -> ThreadPoolExecutor:
        if executor is not None and executor._max_workers == concurrency:
            return executor
        if executor is not None:
            executor.shutdown(wait=False)
        return ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="LLMWikiJob")

    def _poll_concurrent(
        self,
        conn: sqlite3.Connection,
        paths: BrainPaths,
        executor: ThreadPoolExecutor,
        futures: dict[int, tuple[Future[None], bool]],
        concurrency: int,
    ) -> None:
        """Read/write split (ADR 001): dispatch queued jobs to a thread pool,
        keeping write jobs serialized (one at a time) while reads run free."""
        # Reap finished jobs.
        for jid in [j for j, (fut, _) in futures.items() if fut.done()]:
            futures.pop(jid, None)

        if len(futures) >= concurrency:
            time.sleep(0.2)
            return

        write_active = any(is_write for _, is_write in futures.values())
        rows = conn.execute(
            "SELECT id, type, payload FROM jobs "
            "WHERE status = 'queued' ORDER BY id ASC LIMIT 20"
        ).fetchall()

        dispatched = False
        for row in rows:
            job_id = row["id"]
            if job_id in futures:
                continue
            is_write = row["type"] in _WRITE_TYPES
            if is_write and write_active:
                continue  # serialize writes; an ask further down can still run
            payload = json.loads(row["payload"]) if row["payload"] else {}
            self._mark_running(conn, job_id)
            fut = executor.submit(
                self._run_job_threaded, paths, job_id, row["type"], payload
            )
            futures[job_id] = (fut, is_write)
            if is_write:
                write_active = True
            dispatched = True
            if len(futures) >= concurrency:
                break

        if not dispatched:
            time.sleep(0.3)


_worker: JobWorker | None = None

def start_worker() -> None:
    global _worker
    if _worker is None:
        _worker = JobWorker()
        _worker.start()

def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        # Non-blocking or short timeout join so server shutdown is fast
        _worker.join(timeout=2.0)
        _worker = None
