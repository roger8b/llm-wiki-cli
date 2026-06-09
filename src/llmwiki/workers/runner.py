import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..core.config import load_config
from ..core.errors import JobCancelledError, SourceAlreadyProcessedError
from ..core.paths import load_active_brain, resolve_input
from ..db.connection import get_connection, retry_on_locked
from ..db.repo import AskHistoryRepo, JobRepo
from ..services import ingest_service, lint_service, maintenance_service, query_service

logger = logging.getLogger("llmwiki.workers")

class JobWorker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="LLMWikiJobWorker", daemon=True)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

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

                    # Find first queued job
                    cur = conn.execute(
                        "SELECT id, type, payload FROM jobs "
                        "WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
                    )
                    row = cur.fetchone()
                    if not row:
                        time.sleep(1)
                        continue

                    job_id = row["id"]
                    job_type = row["type"]
                    payload_str = row["payload"]
                    payload = json.loads(payload_str) if payload_str else {}

                    # 3. Mark job as running (retry on transient write locks)
                    def _mark_running(c: sqlite3.Connection = conn, jid: int = job_id) -> None:
                        c.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (jid,))
                        c.commit()

                    retry_on_locked(_mark_running)

                    logger.info(f"Processing job {job_id} of type '{job_type}'")

                    # 4. Execute job based on type
                    cfg = load_config(paths)
                    result_data: dict[str, Any] | None = None

                    # Cooperative-cancellation probe for the agent: reads the
                    # cancel_requested flag for THIS job (set by API/CLI on
                    # another connection; WAL makes the committed flag visible).
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
                            res, cr = query_service.ask(
                                question, paths, conn, cfg, save=save, cancel_check=_cancelled
                            )

                            result_data = res.model_dump(mode="json")
                            result_data["change_request_id"] = cr.id if cr else None

                            # Persist to permanent ask history (per-brain).
                            history_id = AskHistoryRepo(conn).insert(
                                question=question,
                                answer=res.answer,
                                citations=json.dumps(
                                    [c.model_dump(mode="json") for c in res.citations]
                                ),
                                change_request_id=cr.id if cr else None,
                            )
                            result_data["history_id"] = history_id
                            JobRepo(conn).complete(job_id, result=json.dumps(result_data))

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
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

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
