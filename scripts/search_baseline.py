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
import tempfile
from datetime import date
from pathlib import Path

from llmwiki.evals.retrieval import (
    collect_meta,
    load_golden,
    render,
    run_ask_eval,
    run_search_eval,
)

_DEFAULT_GOLDEN = Path(__file__).resolve().parents[1] / "evals" / "retrieval" / "golden.yaml"


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
