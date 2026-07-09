#!/usr/bin/env python3
"""Generate an ingestion performance baseline (#270 follow-up, seeds #276/#295).

Runs the *instrumented* ingestion pipeline (#272/#273) against a throwaway brain
that inherits the real global config (`~/.wiki/config.yaml` → MiniMax-M3), over a
fixed set of sample sources, and writes a per-step timing report to
`docs/baselines/`. Touches none of the user's registered brains.

By default the throwaway brain starts EMPTY, which hides every cost that scales
with the size of the wiki — `wiki_stats`, `hybrid_search`, the dedup guardrail
and the extra reads the agent does when there are existing pages to edit (#295).
To measure the cost the user actually feels, seed the throwaway brain to a fixed
size and compare empty vs populated side by side:

- ``--seed-pages N``  seed with N deterministic synthetic pages (CI-friendly).
- ``--seed-brain DIR`` seed from a COPY of a real, already-indexed brain's
  ``wiki/`` (e.g. the desktop brain). The source brain is never mutated — only
  its Markdown is copied into the throwaway and re-indexed.

When a seed is given, every sample is run twice (empty + populated) and the
report shows the per-step delta so the scaling steps are obvious.

Usage:
    python scripts/ingest_baseline.py [--out docs/baselines]
    python scripts/ingest_baseline.py --seed-pages 200
    python scripts/ingest_baseline.py --seed-brain ~/.wiki/brains/desktop
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import tempfile
from datetime import date
from pathlib import Path

from llmwiki.core.config import load_config
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobEventRepo, JobRepo, PageRepo
from llmwiki.services import index_service, ingest_service, scaffold_service

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


_SYNTHETIC_TYPES = ["concept", "entity", "synthesis", "decision", "research", "project"]
# Tool names the agent uses to explore the existing wiki before writing. These
# are the calls that scale with wiki size (#295) — surfaced separately so the
# report shows them growing on a populated brain.
_EXPLORE_TOOLS = frozenset({"search_pages", "related_pages", "read_file", "read_metadata"})


def _seed_synthetic(paths, conn, cfg, pages: int) -> None:
    """Seed the throwaway brain with ``pages`` deterministic synthetic pages.

    Mirrors ``scripts/gen_synthetic_wiki.py`` (fixed seed → reproducible across
    dates) and indexes them so ``wiki_stats``/search/dedup see a real corpus.
    """
    import random  # noqa: PLC0415

    random.seed(42)
    out = paths.wiki / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    titles = [f"Synthetic Page {i:04d}" for i in range(pages)]
    for i, title in enumerate(titles):
        ptype = _SYNTHETIC_TYPES[i % len(_SYNTHETIC_TYPES)]
        targets = (
            random.sample([t for j, t in enumerate(titles) if j != i], k=min(3, pages - 1))
            if pages > 1
            else []
        )
        links = "\n".join(f"- [[{t}]]" for t in targets)
        body = (
            f"---\ntitle: {title}\ntype: {ptype}\ntags: [cluster-{i % 12}]\n---\n\n"
            f"# {title}\n\nSynthetic page for scale testing. Related:\n\n{links}\n"
        )
        (out / f"synthetic-page-{i:04d}.md").write_text(body, encoding="utf-8")
    index_service.reindex(paths, conn, cfg)


def _seed_from_brain(paths, conn, cfg, seed_brain: Path) -> None:
    """Copy an existing brain's ``wiki/`` Markdown into the throwaway and index it.

    Read-only on the source: only ``.md`` files are copied (never the source's
    DB), so the user's real brain is never mutated. The copy is re-indexed here
    so FTS (and embeddings, when configured) reflect the populated corpus.
    """
    src_wiki = Path(seed_brain).expanduser() / "wiki"
    if not src_wiki.is_dir():
        raise SystemExit(f"--seed-brain: no wiki/ under {seed_brain}")
    for md in src_wiki.rglob("*.md"):
        if md.name in {"index.md", "log.md"}:
            continue  # generated files — not real pages
        dest = paths.wiki / md.relative_to(src_wiki)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, dest)
    index_service.reindex(paths, conn, cfg)


def run_one(
    name: str,
    text: str,
    *,
    runner=None,
    outline_runner=None,
    seed_pages: int | None = None,
    seed_brain: Path | None = None,
) -> dict:
    # ``runner``/``outline_runner`` are injectable so the harness is smoke-testable
    # end-to-end without an LLM; left unset they fall through to the real pipeline.
    with tempfile.TemporaryDirectory() as tmp:
        paths = scaffold_service.init_brain(Path(tmp) / "brain", git=False)
        cfg = load_config(paths)  # inherits global MiniMax-M3 config
        conn = get_connection(paths.db_path)
        try:
            if seed_brain is not None:
                _seed_from_brain(paths, conn, cfg, seed_brain)
            elif seed_pages:
                _seed_synthetic(paths, conn, cfg, seed_pages)
            pages_in_brain = len(PageRepo(conn).list())

            src = paths.raw / "articles" / f"{name}.md"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(text, encoding="utf-8")
            extra: dict = {}
            if runner is not None:
                extra["runner"] = runner
            if outline_runner is not None:
                extra["outline_runner"] = outline_runner

            cr = ingest_service.ingest(src, paths, conn, cfg, **extra)
            job = dict(JobRepo(conn).list()[0])
            events = JobEventRepo(conn).since(job["id"], 0)
            result = json.loads(job["result"]) if job["result"] else {}
            kinds: dict[str, int] = {}
            tool_calls_by_name: dict[str, int] = {}
            for e in events:
                kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
                if e["kind"] == "tool_start":
                    payload = dict(e).get("payload")  # sqlite3.Row has no .get
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except (TypeError, ValueError):
                            payload = {}
                    tname = (payload or {}).get("tool", "tool")
                    tool_calls_by_name[tname] = tool_calls_by_name.get(tname, 0) + 1
            explore_calls = sum(
                n for t, n in tool_calls_by_name.items() if t in _EXPLORE_TOOLS
            )
            return {
                "name": name,
                "label": "populated" if (seed_pages or seed_brain) else "empty",
                "pages_in_brain": pages_in_brain,
                "chars": len(text),
                "model": cfg.model,
                "durations_ms": result.get("durations_ms", {}),
                "execution": result.get("execution"),
                "files_changed": cr.files_changed,
                "event_counts": kinds,
                "tool_calls_by_name": tool_calls_by_name,
                "explore_calls": explore_calls,
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
        label = r.get("label", "empty")
        pages = r.get("pages_in_brain", 0)
        heading = f"## {r['name']} — {label} brain ({pages} pages)"
        lines += [
            f"{heading} ({r['chars']:,} chars → {r['files_changed']} pages)",
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
        explore = r.get("explore_calls", 0)
        by_name = r.get("tool_calls_by_name", {})
        lines += [
            "",
            f"Tokens in/out: {ex.get('tokens_in', '?')}/{ex.get('tokens_out', '?')} · "
            f"tool calls: {ex.get('tool_calls', '?')} · "
            f"fallback: {ex.get('used_fallback', '?')}",
            "",
        ]
        by_source = ex.get("tokens_by_source") or {}
        if by_source:
            tot = sum(by_source.values()) or 1
            ranked = sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)
            top = ranked[0][0]
            lines += [
                f"Input by source (re-send accounted, dominant: **{top}**):",
                "",
                "| Source | Input tokens | % |",
                "| --- | ---: | ---: |",
                *[f"| {src} | {n:,} | {n / tot * 100:.0f}% |" for src, n in ranked],
                "",
            ]
        lines += [
            f"Wiki size during run: **{pages} pages** · explore tool calls "
            f"(search/related/read): **{explore}**" + (f" · {by_name}" if by_name else ""),
            "",
            f"Event counts: {r['event_counts']}",
            "",
        ]

    # Empty vs populated: per-step delta for samples run under both (#295). This
    # is the whole point of the populated baseline — show which steps scale with
    # wiki size (wiki_stats, search, dedup, reads) instead of hiding them.
    by_name_label: dict[str, dict[str, dict]] = {}
    for r in runs:
        by_name_label.setdefault(r["name"], {})[r.get("label", "empty")] = r
    paired = [(n, v["empty"], v["populated"]) for n, v in by_name_label.items()
              if "empty" in v and "populated" in v]
    if paired:
        lines += ["## Empty vs populated (cost that scales with wiki size, #295)", ""]
        for name, empty, pop in paired:
            steps = list(dict.fromkeys([*empty["durations_ms"], *pop["durations_ms"]]))
            lines += [
                f"### {name} — empty vs {pop.get('pages_in_brain', 0)}-page brain",
                "",
                "| Step | Empty | Populated | Δ |",
                "| --- | ---: | ---: | ---: |",
            ]
            for step in steps:
                e = empty["durations_ms"].get(step, 0)
                p = pop["durations_ms"].get(step, 0)
                lines.append(
                    f"| {step} | {e / 1000:.1f}s | {p / 1000:.1f}s | {(p - e) / 1000:+.1f}s |"
                )
            lines += [
                f"| **explore tool calls** | {empty.get('explore_calls', 0)} | "
                f"{pop.get('explore_calls', 0)} | "
                f"{pop.get('explore_calls', 0) - empty.get('explore_calls', 0):+d} |",
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
    ap.add_argument(
        "--seed-pages", type=int, default=None,
        help="Also run each sample against a brain seeded with N synthetic pages (#295).",
    )
    ap.add_argument(
        "--seed-brain", type=Path, default=None,
        help="Also run each sample against a COPY of this brain's wiki/ (#295). "
             "The source brain is never mutated.",
    )
    args = ap.parse_args()
    runs = []
    for name, text in SAMPLES.items():
        print(f"→ ingesting {name} ({len(text):,} chars) [empty]…", flush=True)
        runs.append(run_one(name, text))
        print(f"  done: {runs[-1]['durations_ms']}", flush=True)
        if args.seed_pages or args.seed_brain:
            print(f"→ ingesting {name} [populated]…", flush=True)
            runs.append(
                run_one(name, text, seed_pages=args.seed_pages, seed_brain=args.seed_brain)
            )
            print(
                f"  done: {runs[-1]['pages_in_brain']} pages, "
                f"{runs[-1]['durations_ms']}",
                flush=True,
            )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"ingest-{date.today().isoformat()}.md"
    out_file.write_text(render(runs), encoding="utf-8")
    print(f"\nBaseline written to {out_file}")


if __name__ == "__main__":
    main()
