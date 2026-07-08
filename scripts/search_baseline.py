#!/usr/bin/env python3
"""Retrieval eval harness + ask baseline (#349, epic #348).

Measures search quality (recall@5/@10, MRR, latency p50/p95) over a golden set
of queries in 3 modes — keyword (FTS), semantic (vector only) and hybrid (RRF)
— and, with ``--ask``, baselines ``query_service.ask`` (latency, tokens,
tool calls, invalid citations). Follows the ``scripts/ingest_baseline.py``
conventions: throwaway brain seeded from a read-only copy of a real brain,
report published under ``docs/baselines/``.

Usage:
    python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop
    python scripts/search_baseline.py --seed-brain ... --ask --runs 3
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

_CLASSES = {"exact", "paraphrase", "multiword", "vague", "negative"}
_DEFAULT_GOLDEN = Path(__file__).resolve().parents[1] / "evals" / "retrieval" / "golden.yaml"


@dataclass
class GoldenCase:
    id: str
    cls: str
    query: str
    expected: list[str] = field(default_factory=list)


@dataclass
class AskCase:
    id: str
    question: str


def load_golden(path: Path) -> tuple[list[GoldenCase], list[AskCase]]:
    """Parse and validate the golden set. Raises ``ValueError`` on bad cases."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cases: list[GoldenCase] = []
    for raw in data.get("search", []) or []:
        cls = str(raw.get("class", ""))
        if cls not in _CLASSES:
            raise ValueError(
                f"case {raw.get('id')}: unknown class {cls!r} (use {sorted(_CLASSES)})"
            )
        expected = [str(p).lstrip("/") for p in (raw.get("expected") or [])]
        if cls == "negative" and expected:
            raise ValueError(f"case {raw.get('id')}: negative case must have empty expected")
        if cls != "negative" and not expected:
            raise ValueError(f"case {raw.get('id')}: expected pages required for class {cls!r}")
        cases.append(
            GoldenCase(id=str(raw["id"]), cls=cls, query=str(raw["query"]), expected=expected)
        )
    ask_cases = [
        AskCase(id=str(a["id"]), question=str(a["question"])) for a in data.get("ask", []) or []
    ]
    return cases, ask_cases


# --- metrics ----------------------------------------------------------------


def recall_at(expected: list[str], ranked: list[str], k: int) -> float:
    if not expected:
        return 0.0
    top = set(ranked[:k])
    return sum(1 for e in expected if e in top) / len(expected)


def mrr(expected: list[str], ranked: list[str]) -> float:
    want = set(expected)
    for i, path in enumerate(ranked, start=1):
        if path in want:
            return 1.0 / i
    return 0.0


def p50(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(0.95 * len(ordered)) - 1))
    return ordered[idx]


# --- search eval -------------------------------------------------------------


def _rank(conn, cfg, query: str, mode: str, limit: int, embedder, store) -> list[str] | None:
    """Ranked page paths for ``query`` in ``mode``; None when the mode is off."""
    from llmwiki.search.service import hybrid_search, keyword_search

    if mode == "keyword":
        return [h.path for h in keyword_search(conn, query, limit)]
    if mode == "semantic":
        if embedder is None or store is None:
            return None
        vector = embedder.embed(query)
        return [p for p, _t, _s in store.query(vector, limit)]
    return [h.path for h in hybrid_search(conn, query, limit=limit, embedder=embedder, store=store)]


def run_search_eval(conn, cfg, cases: list[GoldenCase], *, limit: int = 10) -> dict:
    """recall@5/@10, MRR, negative hit-rate and latency per mode, per class."""
    from llmwiki.search.factory import build_semantic_backend

    embedder, store = build_semantic_backend(cfg, conn)
    report: dict[str, dict] = {}
    for mode in ("keyword", "semantic", "hybrid"):
        if mode == "semantic" and (embedder is None or store is None):
            report[mode] = {"available": False}
            continue
        latencies: list[float] = []
        r5: list[float] = []
        r10: list[float] = []
        rr: list[float] = []
        neg_hits = 0
        neg_total = 0
        by_class: dict[str, list[float]] = {}
        per_case: list[dict] = []
        for case in cases:
            start = time.perf_counter()
            ranked = _rank(conn, cfg, case.query, mode, limit, embedder, store) or []
            latencies.append((time.perf_counter() - start) * 1000)
            if case.cls == "negative":
                neg_total += 1
                if ranked[:5]:
                    neg_hits += 1
                per_case.append({"id": case.id, "class": case.cls, "hits_top5": len(ranked[:5])})
                continue
            r5.append(recall_at(case.expected, ranked, 5))
            r10.append(recall_at(case.expected, ranked, 10))
            rr.append(mrr(case.expected, ranked))
            by_class.setdefault(case.cls, []).append(recall_at(case.expected, ranked, 5))
            per_case.append(
                {
                    "id": case.id,
                    "class": case.cls,
                    "recall_at_5": r5[-1],
                    "mrr": rr[-1],
                    "top": ranked[:5],
                }
            )
        report[mode] = {
            "available": True,
            "cases": len(cases),
            "recall_at_5": statistics.fmean(r5) if r5 else 0.0,
            "recall_at_10": statistics.fmean(r10) if r10 else 0.0,
            "mrr": statistics.fmean(rr) if rr else 0.0,
            "negative_hit_rate": (neg_hits / neg_total) if neg_total else 0.0,
            "recall_at_5_by_class": {c: statistics.fmean(v) for c, v in by_class.items()},
            "latency_ms_p50": p50(latencies),
            "latency_ms_p95": p95(latencies),
            "per_case": per_case,
        }
    return report


# --- ask baseline ------------------------------------------------------------


def run_ask_eval(
    paths, conn, cfg, ask_cases: list[AskCase], *, runs: int = 3, mode: str = "agent"
) -> dict:
    """Latency / tokens / tool calls / invalid citations for ``ask`` (agent path).

    ``runs`` full passes over the questions; run 1 is discarded as warmup when
    ``runs >= 3`` (docs/baselines convention), aggregates are over the rest.
    """
    from llmwiki.services import query_service

    cfg = cfg.model_copy(update={"ask_mode": mode})
    all_runs: list[list[dict]] = []
    for _run_idx in range(runs):
        results: list[dict] = []
        for case in ask_cases:
            start = time.perf_counter()
            read_meta: dict = {}

            def runner(cfg_, backend, *, question, save, meta_sink=read_meta, **extra):
                from llmwiki.llm_agents.factory import run_query

                result = run_query(cfg_, backend, question=question, save=save, **extra)
                if backend is not None and backend.execution_meta is not None:
                    meta_sink.update(backend.execution_meta.to_dict())
                return result

            def rag_runner(
                cfg_, backend, *, question, context, save, meta_sink=read_meta, **extra
            ):
                from llmwiki.llm_agents.factory import run_query_rag

                result = run_query_rag(
                    cfg_, backend, question=question, context=context, save=save, **extra
                )
                if backend is not None and backend.execution_meta is not None:
                    meta_sink.update(backend.execution_meta.to_dict())
                return result

            result, _cr = query_service.ask(
                case.question, paths, conn, cfg, runner=runner, rag_runner=rag_runner
            )
            latency_ms = (time.perf_counter() - start) * 1000
            invalid = sum(1 for c in result.citations if c.invalid)
            results.append(
                {
                    "id": case.id,
                    "latency_ms": latency_ms,
                    "tokens_in": read_meta.get("tokens_in", 0),
                    "tokens_out": read_meta.get("tokens_out", 0),
                    "tool_calls": read_meta.get("tool_calls", 0),
                    "citations": len(result.citations),
                    "invalid_citations": invalid,
                    "answer_chars": len(result.answer or ""),
                }
            )
        all_runs.append(results)

    kept = all_runs[1:] if runs >= 3 else all_runs
    flat = [r for run in kept for r in run]

    def agg(key: str) -> dict:
        vals = [float(r[key]) for r in flat]
        return {"p50": p50(vals), "p95": p95(vals)}

    return {
        "questions": len(ask_cases),
        "mode": mode,
        "runs": runs,
        "runs_kept": len(kept),
        "latency_ms": agg("latency_ms"),
        "tokens_in": agg("tokens_in"),
        "tokens_out": agg("tokens_out"),
        "tool_calls": agg("tool_calls"),
        "invalid_citations_total": sum(r["invalid_citations"] for r in flat),
        "citations_total": sum(r["citations"] for r in flat),
        "per_question": flat,
    }


# --- report ------------------------------------------------------------------


def collect_meta(conn, cfg, *, pages_in_brain: int) -> dict:
    """Index/embeddings health snapshot for the report header (#303 invariant)."""
    embeddings = conn.execute("SELECT COUNT(*) AS n FROM page_embeddings").fetchone()["n"]
    return {
        "pages": pages_in_brain,
        "page_embeddings": embeddings,
        "embedding_model": cfg.embedding_model,
        "model": cfg.model,
    }


def render(*, search_report: dict, ask_report: dict | None, meta: dict) -> str:
    lines = [
        f"# Search & ask baseline — {date.today().isoformat()}",
        "",
        f"Brain: **{meta['pages']} pages** · `page_embeddings`: **{meta['page_embeddings']}** · "
        f"embedding model: `{meta['embedding_model']}` · ask model: `{meta['model']}`.",
        "",
        "## Retrieval (golden set)",
        "",
        "| Mode | recall@5 | recall@10 | MRR | neg. hit-rate | lat p50 | lat p95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("keyword", "semantic", "hybrid"):
        stats = search_report.get(mode, {})
        if not stats.get("available"):
            lines.append(f"| {mode} | — | — | — | — | — | (unavailable) |")
            continue
        lines.append(
            f"| {mode} | {stats['recall_at_5']:.3f} | {stats['recall_at_10']:.3f} | "
            f"{stats['mrr']:.3f} | {stats['negative_hit_rate']:.2f} | "
            f"{stats['latency_ms_p50']:.1f}ms | {stats['latency_ms_p95']:.1f}ms |"
        )
    lines += ["", "### recall@5 por classe", ""]
    classes = sorted(
        {c for m in search_report.values() for c in (m.get("recall_at_5_by_class") or {})}
    )
    if classes:
        lines.append("| Mode | " + " | ".join(classes) + " |")
        lines.append("| --- |" + " ---: |" * len(classes))
        for mode in ("keyword", "semantic", "hybrid"):
            stats = search_report.get(mode, {})
            if not stats.get("available"):
                continue
            by_class = stats.get("recall_at_5_by_class") or {}
            row = " | ".join(f"{by_class.get(c, 0.0):.3f}" for c in classes)
            lines.append(f"| {mode} | {row} |")
    if ask_report:
        lat, tin, tout, calls = (
            ask_report["latency_ms"],
            ask_report["tokens_in"],
            ask_report["tokens_out"],
            ask_report["tool_calls"],
        )
        lines += [
            "",
            f"## Ask (mode: {ask_report.get('mode', 'agent')})",
            "",
            f"{ask_report['questions']} questions × {ask_report['runs']} runs "
            f"({ask_report['runs_kept']} kept, warmup discarded when runs ≥ 3).",
            "",
            "| Metric | p50 | p95 |",
            "| --- | ---: | ---: |",
            f"| latency | {lat['p50'] / 1000:.1f}s | {lat['p95'] / 1000:.1f}s |",
            f"| tokens_in | {tin['p50']:,.0f} | {tin['p95']:,.0f} |",
            f"| tokens_out | {tout['p50']:,.0f} | {tout['p95']:,.0f} |",
            f"| tool_calls | {calls['p50']:.0f} | {calls['p95']:.0f} |",
            "",
            f"Citations: {ask_report['citations_total']} total, "
            f"**{ask_report['invalid_citations_total']} invalid**.",
        ]
    lines += [
        "",
        "## Reprodução",
        "",
        "```bash",
        "python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop --ask --runs 3",
        "```",
        "",
    ]
    return "\n".join(lines)


# --- seeding (same read-only pattern as ingest_baseline) ---------------------


def _seed_from_brain(paths, conn, cfg, seed_brain: Path) -> int:
    from llmwiki.db.repo import PageRepo
    from llmwiki.services import index_service

    src_wiki = Path(seed_brain).expanduser() / "wiki"
    if not src_wiki.is_dir():
        raise SystemExit(f"--seed-brain: no wiki/ under {seed_brain}")
    for md in src_wiki.rglob("*.md"):
        if md.name in {"index.md", "log.md"}:
            continue
        dest = paths.wiki / md.relative_to(src_wiki)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, dest)
    index_service.reindex(paths, conn, cfg)
    return len(PageRepo(conn).list())


def main() -> None:
    from llmwiki.core.config import load_config
    from llmwiki.db.connection import get_connection
    from llmwiki.services import scaffold_service

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-brain", type=Path, required=True)
    parser.add_argument("--golden", type=Path, default=_DEFAULT_GOLDEN)
    parser.add_argument("--out", type=Path, default=Path("docs/baselines"))
    parser.add_argument("--ask", action="store_true", help="also baseline query_service.ask (LLM)")
    parser.add_argument("--runs", type=int, default=3, help="ask runs (run 1 = warmup)")
    parser.add_argument("--ask-mode", choices=["agent", "rag", "auto"], default="agent")
    parser.add_argument("--tag", default="", help="suffix for the output filename")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    cases, ask_cases = load_golden(args.golden)
    with tempfile.TemporaryDirectory() as tmp:
        paths = scaffold_service.init_brain(Path(tmp) / "brain", git=False)
        cfg = load_config(paths)
        conn = get_connection(paths.db_path)
        try:
            pages = _seed_from_brain(paths, conn, cfg, args.seed_brain)
            meta = collect_meta(conn, cfg, pages_in_brain=pages)
            print(f"brain seeded: {pages} pages, {meta['page_embeddings']} embeddings")
            search_report = run_search_eval(conn, cfg, cases, limit=args.limit)
            ask_report = None
            if args.ask:
                if not ask_cases:
                    raise SystemExit("--ask: golden set has no ask cases")
                ask_report = run_ask_eval(
                    paths, conn, cfg, ask_cases, runs=args.runs, mode=args.ask_mode
                )
            md = render(search_report=search_report, ask_report=ask_report, meta=meta)
        finally:
            conn.close()
    args.out.mkdir(parents=True, exist_ok=True)
    suffix = f"-{args.tag}" if args.tag else ""
    out_file = args.out / f"search-{date.today().isoformat()}{suffix}.md"
    out_file.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nwritten: {out_file}")


if __name__ == "__main__":
    main()
