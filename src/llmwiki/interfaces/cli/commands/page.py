"""Page management subcommands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from ....core.errors import WikiError
from ....core.models import PageType
from ....core.paths import load_active_brain, resolve_input, BrainPaths
from ....services import page_service

page_app = typer.Typer(help="Manage wiki pages.", no_args_is_help=True)


def _brain() -> BrainPaths:
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1)


@page_app.command("create")
def page_create(
    title: str = typer.Argument(..., help="Page title."),
    type_: str = typer.Option("concept", "--type", "-t", help="Page type."),
) -> None:
    """Create a wiki page from the type template."""
    paths = _brain()
    try:
        page_type = PageType(type_)
    except ValueError:
        valid = ", ".join(t.value for t in PageType)
        typer.echo(f"[red]Invalid type '{type_}'. Use one of: {valid}[/red]", err=True)
        raise typer.Exit(code=1)
    try:
        dest = page_service.create_page(title, page_type, paths)
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"[green]Page created:[/green] {paths.relative(dest)}")


@page_app.command("open")
def page_open(path: str = typer.Argument(..., help="Page path.")) -> None:
    """Print the content of a page."""
    paths = _brain()
    try:
        target = resolve_input(path, paths.root)
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1)
    if not target.is_file():
        typer.echo(f"[red]Page not found: {path}[/red]", err=True)
        raise typer.Exit(code=1)
    Console(file=sys.stdout).print(target.read_text(encoding="utf-8"), markup=False)