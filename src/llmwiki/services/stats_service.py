"""Aggregate agent-run telemetry into per-model comparative stats (#176).

Primary source: the ``jobs`` table (``result.execution`` JSON). Runs that
produced a change request without a backing job (e.g. ``wiki maintain`` from the
CLI) are read from the CR ``meta.json``. Each run is attributed to its model and
folded into a :class:`ModelStats` row, with an estimated cost from
``core.pricing`` (``None`` when the model price is unknown).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..core import pricing
from ..core.models import ModelStats
from ..core.paths import BrainPaths


@dataclass
class _Run:
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    used_fallback: bool
    # True/False for ingest runs (CR with 0 files = phantom), None otherwise.
    phantom: bool | None
    cr_status: str | None


def _exec_of(obj: dict[str, object]) -> dict[str, object] | None:
    value = obj.get("execution")
    return value if isinstance(value, dict) and value.get("model") else None


def _to_run(execution: dict[str, object], *, phantom: bool | None, cr_status: str | None) -> _Run:
    def _int(key: str) -> int:
        value = execution.get(key, 0) or 0
        if isinstance(value, (int, float, str)):
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
        return 0

    return _Run(
        model=str(execution["model"]),
        tokens_in=_int("tokens_in"),
        tokens_out=_int("tokens_out"),
        latency_ms=_int("latency_ms"),
        used_fallback=bool(execution.get("used_fallback", False)),
        phantom=phantom,
        cr_status=cr_status,
    )


def _collect_runs(conn: sqlite3.Connection, paths: BrainPaths, since: str | None) -> list[_Run]:
    cr_rows = conn.execute(
        "SELECT id, job_id, status, diff_dir, created_at FROM change_requests"
    ).fetchall()
    cr_status = {r["id"]: r["status"] for r in cr_rows}

    runs: list[_Run] = []
    seen_cr: set[str] = set()

    where = "WHERE result IS NOT NULL"
    params: list[object] = []
    if since:
        where += " AND created_at >= ?"
        params.append(since)
    job_rows = conn.execute(
        f"SELECT type, result FROM jobs {where} ORDER BY created_at DESC", params
    ).fetchall()
    for row in job_rows:
        try:
            result = json.loads(row["result"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(result, dict):
            continue
        execution = _exec_of(result)
        if execution is None:
            continue
        cr_id = result.get("cr") or result.get("change_request_id")
        cr_id = str(cr_id) if cr_id else None
        phantom: bool | None = None
        if row["type"] == "ingest":
            files = result.get("files", result.get("files_changed", 0))
            phantom = (int(files) if isinstance(files, int) else 0) == 0
        runs.append(
            _to_run(execution, phantom=phantom, cr_status=cr_status.get(cr_id) if cr_id else None)
        )
        if cr_id:
            seen_cr.add(cr_id)

    # CRs without a backing job (e.g. CLI maintain) — read execution from meta.
    for r in cr_rows:
        if r["job_id"] is not None or r["id"] in seen_cr:
            continue
        if since and r["created_at"] and r["created_at"] < since:
            continue
        meta_file = Path(r["diff_dir"]) / "meta.json"
        if not meta_file.is_file():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        execution = _exec_of(meta) if isinstance(meta, dict) else None
        if execution is None:
            continue
        runs.append(_to_run(execution, phantom=None, cr_status=r["status"]))
    return runs


def _avg(values: list[int]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    # Nearest-rank percentile.
    rank = max(1, -(-95 * len(ordered) // 100))  # ceil(0.95 * n), at least 1
    return ordered[min(rank, len(ordered)) - 1]


def _build(model: str, runs: list[_Run]) -> ModelStats:
    n = len(runs)
    ti = [r.tokens_in for r in runs]
    to = [r.tokens_out for r in runs]
    lat = [r.latency_ms for r in runs]
    fallback = sum(1 for r in runs if r.used_fallback)
    ingest = [r for r in runs if r.phantom is not None]
    phantoms = sum(1 for r in ingest if r.phantom)
    applied = sum(1 for r in runs if r.cr_status == "applied")
    rejected = sum(1 for r in runs if r.cr_status == "rejected")
    est = pricing.estimate_cost(model, sum(ti), sum(to))
    return ModelStats(
        model=model,
        runs=n,
        tokens_in_avg=_avg(ti),
        tokens_in_p95=_p95(ti),
        tokens_out_avg=_avg(to),
        tokens_out_p95=_p95(to),
        latency_ms_avg=_avg(lat),
        latency_ms_p95=_p95(lat),
        fallback_rate=round(fallback / n, 4) if n else 0.0,
        phantom_rate=round(phantoms / len(ingest), 4) if ingest else 0.0,
        applied=applied,
        rejected=rejected,
        est_cost_usd=est,
    )


def agent_stats(
    conn: sqlite3.Connection, paths: BrainPaths, *, since: str | None = None
) -> list[ModelStats]:
    """Per-model agent telemetry, newest activity first by run count."""
    runs = _collect_runs(conn, paths, since)
    by_model: dict[str, list[_Run]] = {}
    for r in runs:
        by_model.setdefault(r.model, []).append(r)
    stats = [_build(model, group) for model, group in by_model.items()]
    stats.sort(key=lambda s: s.runs, reverse=True)
    return stats
