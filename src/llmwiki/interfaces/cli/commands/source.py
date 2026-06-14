"""Source management subcommands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape as esc
from rich.table import Table

from ....core.config import load_config
from ....core.errors import WikiError
from ....core.paths import BrainPaths, load_active_brain
from ....db.connection import get_connection
from ....db.repo import SourceRepo
from ....sources.manager import add_source, add_url

source_app = typer.Typer(
    help="Manage raw sources in raw/.",
    no_args_is_help=True,
)


def _brain() -> BrainPaths:
    """Resolve the active brain from the shared registry."""
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


@source_app.command("add")
def source_add(
    file: str = typer.Argument(None, help="Source file."),
    url: str = typer.Option(None, "--url", help="Capture a web article by URL."),
) -> None:
    """Register a raw file in raw/, or capture a web article with ``--url``."""
    if bool(file) == bool(url):
        typer.echo(
            "[red]Provide exactly one of a file argument or --url.[/red]", err=True
        )
        raise typer.Exit(code=2)
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        if url:
            cfg = load_config(paths)
            result = add_url(
                url, paths, SourceRepo(conn), timeout=cfg.request_timeout
            )
        else:
            src = Path(file).resolve()
            if not src.is_file():
                typer.echo(f"[red]File not found: {file}[/red]", err=True)
                raise typer.Exit(code=3)
            result = add_source(src, paths, SourceRepo(conn))
    finally:
        conn.close()
    if result.already_present:
        typer.echo(
            f"[yellow]Source already registered[/yellow] (matching hash): {result.source.path}"
        )
    else:
        title = f" — {result.source.title}" if result.source.title else ""
        typer.echo(
            f"[green]Source registered:[/green] {result.source.path}{title} "
            f"({result.source.status.value})"
        )


@source_app.command("list")
def source_list() -> None:
    """List registered sources."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        sources = SourceRepo(conn).list()
    finally:
        conn.close()
    if not sources:
        typer.echo("[dim]No sources registered.[/dim]")
        return
    table = Table("Path", "Type", "Status", "Title")
    for s in sources:
        table.add_row(esc(s.path), s.type, s.status.value, esc(s.title or ""))
    Console(file=sys.stdout).print(table)