"""Ingest command: read a source with the LLM and create a change request."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape as esc

from ....core.config import load_config
from ....core.errors import WikiError
from ....core.paths import load_active_brain, resolve_input
from ....db.connection import get_connection
from ....services import ingest_service


def _brain():
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1)


def ingest(file: str = typer.Argument(..., help="Source file to ingest.")) -> None:
    """Read a source with the LLM and create a change request (does not write to the wiki).

    Accepts a path within the brain (e.g. raw/articles/x.md) or any
    readable system file.
    """
    paths = _brain()
    direct = Path(file)
    target = direct if direct.is_file() else (paths.root / file)
    if not target.is_file():
        typer.echo(f"[red]File not found: {file}[/red]", err=True)
        raise typer.Exit(code=1)
    target = target.resolve()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        cr = ingest_service.ingest(target, paths, conn, cfg)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Ingestion failed: {exc}[/red]", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()
    typer.echo(f"[green]Source processed[/green] (model: {cfg.model}).")
    for c in cr.changes:
        mark = "+" if c.operation == "create" else "~"
        typer.echo(f"  {mark} {esc(c.path)} ({c.operation})")
    if cr.files_changed == 0:
        typer.echo(
            f"[yellow]Warning: the model did not write any pages[/yellow] "
            f"(empty CR {cr.id}). Small models often fail at this — "
            f"use a model with good tool calling support."
        )
        return
    typer.echo(f"Change request created: [bold]{cr.id}[/bold] ({cr.files_changed} files)")
    typer.echo(f"Review with:  wiki review {cr.id}")