import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from ..core.config import load_config
from ..core.paths import load_active_brain, resolve_input
from ..db.connection import get_connection
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
        logger.info("Background job worker started.")
        # Track which DBs already had their schema applied, so the idle poll loop
        # opens lightweight connections instead of re-running schema.sql (and the
        # FTS5 virtual-table creation) every second.
        initialized: set[Path] = set()
        while not self._stop_event.is_set():
            try:
                # 1. Load active brain
                try:
                    paths = load_active_brain()
                except Exception:
                    # No active brain registered yet, wait and try again
                    time.sleep(2)
                    continue

                # 2. Open DB connection (apply schema once per DB path)
                needs_schema = paths.db_path not in initialized
                conn = get_connection(paths.db_path, apply_schema=needs_schema)
                if needs_schema:
                    initialized.add(paths.db_path)
                try:
                    # Find first queued job
                    cur = conn.execute(
                        "SELECT id, type, payload FROM jobs "
                        "WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
                    )
                    row = cur.fetchone()
                    if not row:
                        conn.close()
                        time.sleep(1)
                        continue

                    job_id = row["id"]
                    job_type = row["type"]
                    payload_str = row["payload"]
                    payload = json.loads(payload_str) if payload_str else {}

                    # 3. Mark job as running
                    conn.execute(
                        "UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,)
                    )
                    conn.commit()

                    logger.info(f"Processing job {job_id} of type '{job_type}'")

                    # 4. Execute job based on type
                    cfg = load_config(paths)
                    result_data: dict[str, Any] | None = None

                    try:
                        if job_type == "ingest":
                            source_path = payload.get("source")
                            if not source_path:
                                raise ValueError("Missing 'source' path in ingest payload")
                            target = resolve_input(source_path, paths.root)
                            # Run ingest service. It handles its own job completion using job_id.
                            ingest_service.ingest(target, paths, conn, cfg, job_id=job_id)

                        elif job_type == "maintain":
                            semantic = payload.get("semantic", False)
                            if semantic:
                                findings = lint_service.lint_all(paths, cfg, semantic=True)
                            else:
                                findings = lint_service.lint_structural(paths)

                            cr = maintenance_service.maintain(findings, paths, conn, cfg)
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
                            res, cr = query_service.ask(question, paths, conn, cfg, save=save)

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

                    except Exception as exc:
                        logger.exception(f"Error processing job {job_id}")
                        # In case the service raised but didn't complete:
                        try:
                            JobRepo(conn).complete(job_id, error=str(exc))
                        except Exception:
                            logger.exception(f"Failed to mark job {job_id} as failed in DB")

                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            except Exception:
                logger.exception("Error in job worker loop")
                time.sleep(2)

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
