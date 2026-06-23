#!/usr/bin/env python3
"""Generate an ingestion performance baseline (#270 follow-up, seeds #276).

Runs the *instrumented* ingestion pipeline (#272/#273) against a throwaway brain
that inherits the real global config (`~/.wiki/config.yaml` → MiniMax-M3), over a
fixed set of sample sources, and writes a per-step timing report to
`docs/baselines/`. Touches none of the user's registered brains.

Usage:
    python scripts/ingest_baseline.py [--out docs/baselines]
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from datetime import date
from pathlib import Path

from llmwiki.core.config import load_config
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobEventRepo, JobRepo
from llmwiki.services import ingest_service, scaffold_service

# Small, deterministic sources covering the single-pass and multi-chunk paths.
SHORT = """# Retrieval-Augmented Generation (RAG)

RAG combines a retriever over an external corpus with a generator (an LLM). At
query time the retriever fetches the most relevant passages and the generator
conditions its answer on them, grounding output in sources and reducing
hallucination. Key components are the embedding model, the vector store, the
chunking strategy and the re-ranker. Variants include naive RAG, advanced RAG
with query rewriting, and self-RAG where the model decides when to retrieve.
"""


def _long_source() -> str:
    blocks = []
    concepts = [
        "Vector Store", "Embedding Model", "Chunking", "Re-ranking",
        "Query Rewriting", "Hybrid Search", "Evaluation", "Self-RAG",
    ]
    filler = "This section explains the concept in practical detail. " * 30
    for rep in range(4):
        for c in concepts:
            blocks.append(f"## {c} (part {rep})\n\n{filler}\n")
    return "\n\n".join(blocks)


SAMPLES = {"short_single_pass": SHORT, "long_multi_chunk": _long_source()}


def run_one(name: str, text: str, *, runner=None, outline_runner=None) -> dict:
    # ``runner``/``outline_runner`` are injectable so the harness is smoke-testable
    # end-to-end without an LLM; left unset they fall through to the real pipeline.
    with tempfile.TemporaryDirectory() as tmp:
        paths = scaffold_service.init_brain(Path(tmp) / "brain", git=False)
        cfg = load_config(paths)  # inherits global MiniMax-M3 config
        src = paths.raw / "articles" / f"{name}.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(text, encoding="utf-8")
        conn = get_connection(paths.db_path)
        extra: dict = {}
        if runner is not None:
            extra["runner"] = runner
        if outline_runner is not None:
            extra["outline_runner"] = outline_runner
        try:
            cr = ingest_service.ingest(src, paths, conn, cfg, **extra)
            job = dict(JobRepo(conn).list()[0])
            events = JobEventRepo(conn).since(job["id"], 0)
            result = json.loads(job["result"]) if job["result"] else {}
            kinds: dict[str, int] = {}
            for e in events:
                kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
            return {
                "name": name,
                "chars": len(text),
                "model": cfg.model,
                "durations_ms": result.get("durations_ms", {}),
                "execution": result.get("execution"),
                "files_changed": cr.files_changed,
                "event_counts": kinds,
            }
        finally:
            conn.close()


def render(runs: list[dict]) -> str:
    lines = [
        f"# Ingestion baseline — {date.today().isoformat()}",
        "",
        f"Model: `{runs[0]['model'] if runs else 'n/a'}` · pipeline instrumented by #272/#273.",
        "",
    ]
    for r in runs:
        total = sum(r["durations_ms"].values())
        lines += [
            f"## {r['name']} ({r['chars']:,} chars → {r['files_changed']} pages)",
            "",
            f"Total instrumented time: **{total / 1000:.1f}s**",
            "",
            "| Step | Duration |",
            "| --- | ---: |",
        ]
        for step, ms in r["durations_ms"].items():
            pct = (ms / total * 100) if total else 0
            lines.append(f"| {step} | {ms / 1000:.1f}s ({pct:.0f}%) |")
        ex = r["execution"] or {}
        lines += [
            "",
            f"Tokens in/out: {ex.get('tokens_in', '?')}/{ex.get('tokens_out', '?')} · "
            f"tool calls: {ex.get('tool_calls', '?')} · "
            f"fallback: {ex.get('used_fallback', '?')}",
            "",
            f"Event counts: {r['event_counts']}",
            "",
        ]
    # Dominant bottleneck across runs (guides #277–#279 priorities).
    agg: dict[str, list[float]] = {}
    for r in runs:
        for step, ms in r["durations_ms"].items():
            agg.setdefault(step.split(" ")[0], []).append(ms)
    if agg:
        lines += ["## Dominant steps (median ms across runs)", ""]
        ranked = sorted(agg.items(), key=lambda kv: statistics.median(kv[1]), reverse=True)
        for step, vals in ranked:
            lines.append(f"- **{step}**: {statistics.median(vals) / 1000:.1f}s median")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/baselines")
    args = ap.parse_args()
    runs = []
    for name, text in SAMPLES.items():
        print(f"→ ingesting {name} ({len(text):,} chars)…", flush=True)
        runs.append(run_one(name, text))
        print(f"  done: {runs[-1]['durations_ms']}", flush=True)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"ingest-{date.today().isoformat()}.md"
    out_file.write_text(render(runs), encoding="utf-8")
    print(f"\nBaseline written to {out_file}")


if __name__ == "__main__":
    main()
