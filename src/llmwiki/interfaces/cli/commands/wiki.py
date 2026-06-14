"""Core wiki commands: index, search, lint, ask, maintain, log."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.markup import escape as esc
from rich.table import Table

from ....core.config import load_config
from ....core.errors import WikiError
from ....core.models import Severity
from ....core.paths import BrainPaths, load_active_brain
from ....db.connection import get_connection
from ....db.repo import PageFtsRepo
from ....services import (
    change_request_service,
    index_service,
    lint_service,
    query_service,
)
from .._output import emit

console = Console()


def _brain() -> BrainPaths:
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


def index() -> None:
    """Rebuild metadata and regenerate wiki/index.md."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        report = index_service.reindex(paths, conn)
        index_service.rebuild_index_md(paths, conn)
    finally:
        conn.close()
    typer.echo(
        f"[green]Index updated:[/green] {report.pages_indexed} pages, "
        f"{report.links_indexed} links."
    )
    if report.skipped:
        typer.echo(
            f"[yellow]Skipped (invalid frontmatter):[/yellow] "
            f"{', '.join(report.skipped)}"
        )


def search(
    query: str = typer.Argument(..., help="Search query (FTS5)."),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Search pages by keyword (FTS5 index)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        results = PageFtsRepo(conn).search(query)
    finally:
        conn.close()
    payload = {
        "results": [
            {"path": path, "title": title, "score": -rank, "source": "keyword"}
            for path, title, rank in results
        ]
    }

    def human() -> None:
        if not results:
            typer.echo("[dim]No results found.[/dim]")
            return
        table = Table("Page", "Title")
        for path, title, _rank in results:
            table.add_row(esc(path), esc(title))
        Console(file=sys.stdout).print(table)

    emit(payload, as_json=as_json, human=human)


def lint(
    semantic: bool = typer.Option(
        False, "--all/--structural", help="--all includes semantic audit via LLM."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Audit the health of the wiki (structural; --all adds semantic via LLM)."""
    paths = _brain()
    if semantic:
        cfg = load_config(paths)
        try:
            findings = lint_service.lint_all(paths, cfg, semantic=True)
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"[red]Semantic lint failed: {exc}[/red]", err=True)
            raise typer.Exit(code=1) from exc
    else:
        findings = lint_service.lint_structural(paths)
    errors = sum(1 for f in findings if f.severity == Severity.error)
    payload = {"findings": findings}

    def human() -> None:
        if not findings:
            typer.echo("[green]Lint OK — no issues found.[/green]")
            return
        color = {Severity.info: "blue", Severity.warn: "yellow", Severity.error: "red"}
        for f in findings:
            typer.echo(
                f"[{color[f.severity]}]{f.severity.value.upper()}[/] "
                f"{esc(f.kind)}: {esc(f.message)}"
            )

    emit(payload, as_json=as_json, human=human)
    if errors:
        raise typer.Exit(code=1)


def ask(
    question: str = typer.Argument(..., help="Question for the wiki."),
    save: bool = typer.Option(False, "--save", help="Save the answer as a page (creates CR)."),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Answer a question using the wiki as the primary source."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        result, cr = query_service.ask(question, paths, conn, cfg, save=save)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Query failed: {exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()
    payload = {
        "answer": result.answer,
        "citations": [c.model_dump(mode="json") for c in result.citations],
        "suggested_page": (
            result.suggested_page.model_dump(mode="json")
            if result.suggested_page is not None
            else None
        ),
        "change_request_id": cr.id if cr is not None else None,
    }

    def human() -> None:
        Console(file=sys.stdout).print(result.answer, markup=False)
        if result.citations:
            typer.echo("\n[dim]Sources:[/dim]")
            for i, c in enumerate(result.citations, 1):
                ref = c.page or c.source or "?"
                if c.invalid:
                    typer.echo(f"  [{i}] [yellow](!) {esc(ref)} — não resolve[/yellow]")
                else:
                    typer.echo(f"  [{i}] {esc(ref)}")
        if cr is not None:
            typer.echo(
                f"\n[green]Answer saved as change request {cr.id}[/green] "
                f"— review with wiki review {cr.id}"
            )

    emit(payload, as_json=as_json, human=human)


def maintain(
    apply_now: bool = typer.Option(False, "--apply", help="Apply the maintenance CR directly."),
) -> None:
    """Detect issues (lint --all) and propose fixes as a change request."""
    from ....services import maintenance_service

    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        findings = lint_service.lint_all(paths, cfg, semantic=True)
        cr = maintenance_service.maintain(findings, paths, conn, cfg)
        if cr is None:
            typer.echo("[green]Nothing to correct.[/green]")
            return
        typer.echo(
            f"[green]Maintenance CR created: {cr.id}[/green] "
            f"({cr.files_changed} files)"
        )
        if apply_now:
            change_request_service.apply(cr.id, paths, conn)
            typer.echo(f"[green]Applied {cr.id}.[/green]")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Maintenance failed: {exc}[/red]", err=True)
        raise typer.Exit(code=1) from None
    finally:
        conn.close()


def log(
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Print wiki/log.md."""
    paths = _brain()
    if not paths.log_path.is_file():
        if as_json:
            print('{"entries": []}')
            return
        typer.echo("[red]log.md not found.[/red]", err=True)
        raise typer.Exit(code=1)
    text = paths.log_path.read_text(encoding="utf-8")

    def human() -> None:
        Console(file=sys.stdout).print(text, markup=False)

    # Entries are the markdown blocks separated by blank lines; expose them as a
    # list while keeping the raw text for round-tripping.
    entries = [block.strip() for block in text.split("\n\n") if block.strip()]
    emit({"entries": entries, "raw": text}, as_json=as_json, human=human)