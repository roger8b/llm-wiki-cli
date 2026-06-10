"""Evals command: run the agent quality harness over a dataset (issue #175)."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ....core.config import load_config
from ....core.errors import WikiError
from ....core.paths import BrainPaths, load_active_brain

evals_app = typer.Typer(help="Reproducible quality evals for the agents.", no_args_is_help=True)

_DEFAULT_DATASET = Path("tests/evals/dataset")


def _brain() -> BrainPaths:
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


@evals_app.command("run")
def run(
    dataset: Path = typer.Option(  # noqa: B008
        _DEFAULT_DATASET, "--dataset", help="Dataset directory of test sources."
    ),
    json_out: bool = typer.Option(False, "--json", help="Print only JSON to stdout."),
    keep_brain: bool = typer.Option(
        False, "--keep-brain", help="Keep the throwaway brain (for debugging)."
    ),
) -> None:
    """Ingest the dataset into a throwaway brain and score the ingestion agent.

    Uses the configured LLM. Writes a JSON report to
    ``evals/results/<ts>-<model>.json`` in the current directory. With ``--json``
    stdout carries ONLY the report; all other output goes to stderr.
    """
    from ....services import evals_service

    if not dataset.is_dir():
        typer.echo(
            f"[red]Dataset directory not found: {dataset}[/red] "
            "Pass --dataset or run from the repo root.",
            err=True,
        )
        raise typer.Exit(code=1)

    paths = _brain()
    cfg = load_config(paths)

    err = Console(stderr=True)
    if not json_out:
        err.print(f"[dim]Running evals with model {cfg.model}…[/dim]")

    try:
        report = evals_service.run_evals(cfg, dataset_dir=dataset, keep_brain=keep_brain)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Evals failed: {exc}[/red]", err=True)
        raise typer.Exit(code=1) from None

    out_file = evals_service.write_result_json(report, Path.cwd())

    if json_out:
        # stdout: JSON only.
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
        err.print(f"[dim]Report written to {out_file}[/dim]")
        return

    table = Table("Case", "Score", "Pages", "Links", "FM%", "Notes")
    for c in report.cases:
        notes = "; ".join(c.notes)[:48]
        pages = f"{c.pages_created}+{c.pages_updated}"
        links = f"{c.link_resolved}/{c.link_total}"
        fm = f"{int(c.frontmatter_valid_pct * 100)}%"
        score_str = f"{c.score:.0f}"
        if c.score < 60:
            score_str = f"[red]{score_str}[/red]"
        table.add_row(c.name, score_str, pages, links, fm, notes)
    console = Console()
    console.print(table)
    console.print(
        f"\n[bold]Aggregate score: {report.score:.1f}[/bold] "
        f"(model {report.model}, tokens in/out {report.total_tokens_in}/"
        f"{report.total_tokens_out})"
    )
    console.print(f"[dim]Report written to {out_file}[/dim]")
