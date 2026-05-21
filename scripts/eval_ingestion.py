#!/usr/bin/env python3
"""Ingestion evaluation harness.

Runs ingestion against a test corpus, scores the output, and saves results so
successive runs can be compared.

Usage:
    python scripts/eval_ingestion.py                        # run once, print results
    python scripts/eval_ingestion.py --model ollama:qwen2.5:7b
    python scripts/eval_ingestion.py --rounds 2             # run N rounds
    python scripts/eval_ingestion.py --compare              # diff last two result files
    python scripts/eval_ingestion.py --source path/to/doc.md  # custom source

Results saved to: scripts/eval_results/<timestamp>.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root on sys.path so we can import llmwiki without installing
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from llmwiki.agents.backend import ChangeRequestBackend  # noqa: E402
from llmwiki.agents import factory as agent_factory  # noqa: E402
from llmwiki.core.config import WorkspaceConfig  # noqa: E402
from llmwiki.core.paths import BrainPaths  # noqa: E402
from llmwiki.services import scaffold_service  # noqa: E402

# ---------------------------------------------------------------------------
# Test corpus
# ---------------------------------------------------------------------------
DEFAULT_SOURCE_TEXT = """\
# Retrieval-Augmented Generation (RAG)

Retrieval-Augmented Generation (RAG) is a technique that combines a retrieval
system with a generative language model to produce grounded, factual answers.

## How it works
1. **Retrieval**: Given a user query, a retriever (usually dense vector search)
   finds the top-k relevant document chunks from a corpus.
2. **Augmentation**: The retrieved chunks are prepended to the prompt as context.
3. **Generation**: The LLM generates an answer conditioned on the context.

## Key components
- **Embedding model**: Encodes documents and queries into dense vectors.
- **Vector store**: Stores and searches embeddings (FAISS, Pinecone, Chroma).
- **Chunking strategy**: Documents split into overlapping windows (512 tokens
  with 64-token overlap is common).
- **Re-ranker**: Optional cross-encoder that reorders retrieved candidates.

## Variants
- **Naive RAG**: Basic retrieve-then-generate pipeline.
- **Advanced RAG**: Adds query rewriting, iterative retrieval, re-ranking.
- **Modular RAG**: Composable pipeline where each step is swappable.
- **Self-RAG**: Model decides when to retrieve and reflects on retrieved chunks.

## Trade-offs
- Reduces hallucination by grounding responses in retrieved context.
- Retrieval quality limits generation quality (garbage in, garbage out).
- Latency overhead from retrieval step.
- Chunking strategy heavily affects recall.

## Related concepts
- Vector databases
- Semantic search
- Prompt engineering
- Knowledge graphs
- Fine-tuning vs RAG
"""

EVAL_RESULTS_DIR = REPO_ROOT / "scripts" / "eval_results"
EVAL_RESULTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

REQUIRED_FRONTMATTER_FIELDS = {"title", "type", "tags", "sources", "updated_at", "confidence"}
VALID_TYPES = {"concept", "entity", "source_summary", "synthesis", "decision", "project", "research"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_DIRS = {"wiki/concepts", "wiki/entities", "wiki/synthesis", "wiki/decisions",
              "wiki/projects", "wiki/research"}


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter keys from a markdown file."""
    import yaml
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}


def score_page(path: str, content: str) -> dict:
    """Score a single generated page. Returns a dict of check results."""
    checks: dict[str, bool | str] = {}
    fm = _parse_frontmatter(content)

    # --- frontmatter completeness ---
    missing = REQUIRED_FRONTMATTER_FIELDS - set(fm.keys())
    checks["frontmatter_complete"] = len(missing) == 0
    checks["frontmatter_missing"] = sorted(missing)

    # --- type validity ---
    checks["type_valid"] = fm.get("type") in VALID_TYPES

    # --- confidence validity ---
    checks["confidence_valid"] = fm.get("confidence") in VALID_CONFIDENCE

    # --- correct directory ---
    page_type = fm.get("type", "")
    expected_dir = f"wiki/{page_type}s" if page_type else ""
    checks["correct_dir"] = any(path.startswith(d + "/") for d in VALID_DIRS)

    # --- has sources ---
    sources = fm.get("sources", [])
    checks["has_sources"] = isinstance(sources, list) and len(sources) > 0

    # --- has internal links ---
    links = re.findall(r"\[\[([^\]]+)\]\]", content)
    checks["has_internal_links"] = len(links) > 0
    checks["internal_link_count"] = len(links)

    # --- body length (beyond frontmatter) ---
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()
    checks["body_length"] = len(body)
    checks["body_substantial"] = len(body) >= 200

    # --- has headings ---
    headings = re.findall(r"^#{1,3} .+", content, re.MULTILINE)
    checks["has_headings"] = len(headings) > 0

    return checks


def score_run(pages: dict[str, str]) -> dict:
    """Aggregate scores across all pages produced in a run."""
    if not pages:
        return {
            "total_pages": 0,
            "score": 0.0,
            "details": {},
            "summary": "No pages written — ingestion produced empty output.",
        }

    page_scores = {}
    for path, content in pages.items():
        page_scores[path] = score_page(path, content)

    n = len(pages)

    # Granularity score: 1 page = 0%, 3 pages = 50%, ≥5 pages = 100%
    # Encourages extracting multiple concepts from rich sources.
    granularity = min(1.0, max(0.0, (n - 1) / 4.0))

    metrics = {
        "frontmatter_complete": sum(1 for s in page_scores.values() if s["frontmatter_complete"]) / n,
        "type_valid":           sum(1 for s in page_scores.values() if s["type_valid"]) / n,
        "confidence_valid":     sum(1 for s in page_scores.values() if s["confidence_valid"]) / n,
        "correct_dir":          sum(1 for s in page_scores.values() if s["correct_dir"]) / n,
        "has_sources":          sum(1 for s in page_scores.values() if s["has_sources"]) / n,
        "has_internal_links":   sum(1 for s in page_scores.values() if s["has_internal_links"]) / n,
        "body_substantial":     sum(1 for s in page_scores.values() if s["body_substantial"]) / n,
        "has_headings":         sum(1 for s in page_scores.values() if s["has_headings"]) / n,
        "granularity":          granularity,
    }

    # Weighted composite score
    weights = {
        "frontmatter_complete": 2.0,
        "type_valid":           1.5,
        "confidence_valid":     1.0,
        "correct_dir":          1.5,
        "has_sources":          2.0,
        "has_internal_links":   1.5,
        "body_substantial":     2.0,
        "has_headings":         1.0,
        "granularity":          2.5,  # high weight — key KPI
    }
    total_weight = sum(weights.values())
    score = sum(metrics[k] * weights[k] for k in weights) / total_weight

    return {
        "total_pages": n,
        "score": round(score * 100, 1),
        "metrics": {k: round(v * 100, 1) for k, v in metrics.items()},
        "details": page_scores,
        "avg_body_length": int(sum(s["body_length"] for s in page_scores.values()) / n),
        "avg_links_per_page": round(sum(s["internal_link_count"] for s in page_scores.values()) / n, 1),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_ingestion_eval(
    model: str,
    source_text: str,
    source_name: str = "eval/test_source.md",
) -> dict:
    """Run one ingestion round and return the scored result."""
    with tempfile.TemporaryDirectory(prefix="llmwiki-eval-") as tmp:
        brain_path = Path(tmp) / "brain"
        brain = scaffold_service.init_brain(brain_path, git=False)

        cfg = WorkspaceConfig(brain_root=brain.root, model=model)
        backend = ChangeRequestBackend(brain.root)

        print(f"  → model: {model}")
        print(f"  → source: {source_name} ({len(source_text)} chars)")

        try:
            result = agent_factory.run_ingestion(
                cfg, backend,
                source_path=source_name,
                source_text=source_text,
            )
            summary = result.summary if hasattr(result, "summary") else str(result)
        except Exception as exc:
            return {
                "model": model,
                "source": source_name,
                "error": str(exc),
                "score": {"total_pages": 0, "score": 0.0},
            }

        pages = dict(backend.staging)
        scored = score_run(pages)

        return {
            "model": model,
            "source": source_name,
            "agent_summary": summary,
            "pages": list(pages.keys()),
            "score": scored,
        }


# ---------------------------------------------------------------------------
# Compare two result files
# ---------------------------------------------------------------------------

def compare_results(files: list[Path]) -> None:
    """Print a side-by-side comparison of the last two result files."""
    if len(files) < 2:
        print("Need at least 2 result files to compare.")
        return

    a_path, b_path = files[-2], files[-1]
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())

    print(f"\n{'='*60}")
    print(f"COMPARISON")
    print(f"  A: {a_path.name}")
    print(f"  B: {b_path.name}")
    print(f"{'='*60}")

    for i, (ra, rb) in enumerate(zip(a["runs"], b["runs"])):
        sa = ra["score"]
        sb = rb["score"]
        print(f"\nRun {i+1} — model: {ra['model']}")
        print(f"  {'Metric':<25} {'A':>8} {'B':>8} {'Δ':>8}")
        print(f"  {'-'*49}")
        print(f"  {'total_pages':<25} {sa.get('total_pages',0):>8} {sb.get('total_pages',0):>8} "
              f"{sb.get('total_pages',0)-sa.get('total_pages',0):>+8}")
        print(f"  {'composite_score':<25} {sa.get('score',0):>7.1f}% {sb.get('score',0):>7.1f}% "
              f"{sb.get('score',0)-sa.get('score',0):>+7.1f}%")

        metrics_a = sa.get("metrics", {})
        metrics_b = sb.get("metrics", {})
        for k in sorted(set(list(metrics_a) + list(metrics_b))):
            va = metrics_a.get(k, 0)
            vb = metrics_b.get(k, 0)
            delta = vb - va
            flag = " ✓" if delta > 0 else (" ✗" if delta < 0 else "")
            print(f"  {k:<25} {va:>7.1f}% {vb:>7.1f}% {delta:>+7.1f}%{flag}")

        print(f"\n  Pages A: {ra.get('pages', [])}")
        print(f"  Pages B: {rb.get('pages', [])}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingestion eval harness")
    parser.add_argument("--model", default="ollama:gemma4:31b-cloud",
                        help="Model string (default: ollama:gemma4:31b-cloud)")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Number of eval rounds to run (default: 1)")
    parser.add_argument("--source", type=str, default=None,
                        help="Path to a custom source file (default: built-in RAG corpus)")
    parser.add_argument("--compare", action="store_true",
                        help="Compare the last two result files and exit")
    args = parser.parse_args()

    if args.compare:
        files = sorted(EVAL_RESULTS_DIR.glob("*.json"))
        compare_results(files)
        return

    # Load source text
    if args.source:
        source_path = Path(args.source)
        source_text = source_path.read_text(encoding="utf-8")
        source_name = str(source_path)
    else:
        source_text = DEFAULT_SOURCE_TEXT
        source_name = "eval/rag_overview.md"

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_file = EVAL_RESULTS_DIR / f"{timestamp}.json"

    all_runs = []
    for round_num in range(1, args.rounds + 1):
        print(f"\n{'='*60}")
        print(f"Round {round_num}/{args.rounds}")
        print(f"{'='*60}")
        run = run_ingestion_eval(args.model, source_text, source_name)
        all_runs.append(run)
        _print_run_summary(run, round_num)

    output = {
        "timestamp": timestamp,
        "model": args.model,
        "source": source_name,
        "rounds": args.rounds,
        "runs": all_runs,
    }
    result_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n✓ Results saved → {result_file}")

    # If multiple rounds, print aggregate
    if args.rounds > 1:
        _print_aggregate(all_runs)


def _print_run_summary(run: dict, round_num: int) -> None:
    score = run["score"]
    print(f"\nRound {round_num} results:")
    if "error" in run:
        print(f"  ❌ ERROR: {run['error']}")
        return
    print(f"  Pages written : {score['total_pages']}")
    print(f"  Composite     : {score['score']:.1f}%")
    print(f"  Avg body len  : {score.get('avg_body_length', 0)} chars")
    print(f"  Avg links/page: {score.get('avg_links_per_page', 0)}")
    print(f"\n  Metric breakdown:")
    for k, v in score.get("metrics", {}).items():
        bar = "█" * int(v / 10) + "░" * (10 - int(v / 10))
        print(f"    {k:<25} {bar} {v:.0f}%")
    print(f"\n  Pages:")
    for p in run.get("pages", []):
        print(f"    + {p}")
    if run.get("agent_summary"):
        summary = str(run["agent_summary"])[:200]
        print(f"\n  Agent summary: {summary}")

    # Per-page issues
    issues = []
    for path, checks in score.get("details", {}).items():
        page_issues = []
        if not checks.get("frontmatter_complete"):
            page_issues.append(f"missing frontmatter: {checks.get('frontmatter_missing')}")
        if not checks.get("type_valid"):
            page_issues.append("invalid type")
        if not checks.get("has_internal_links"):
            page_issues.append("no internal links")
        if not checks.get("body_substantial"):
            page_issues.append(f"thin body ({checks.get('body_length', 0)} chars)")
        if page_issues:
            issues.append(f"    {path}: {', '.join(page_issues)}")
    if issues:
        print(f"\n  ⚠ Issues found:")
        for issue in issues:
            print(issue)
    else:
        print(f"\n  ✓ No issues found")


def _print_aggregate(runs: list[dict]) -> None:
    valid = [r for r in runs if "error" not in r]
    if not valid:
        print("\nAll rounds errored.")
        return
    avg_score = sum(r["score"]["score"] for r in valid) / len(valid)
    avg_pages = sum(r["score"]["total_pages"] for r in valid) / len(valid)
    print(f"\n{'='*60}")
    print(f"AGGREGATE ({len(valid)}/{len(runs)} successful rounds)")
    print(f"  avg composite score : {avg_score:.1f}%")
    print(f"  avg pages written   : {avg_pages:.1f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
