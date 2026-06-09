"""Ingest command: read a source with the LLM and create a change request."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape as esc

from ....core.config import load_config
from ....core.errors import SourceAlreadyProcessedError, WikiError
from ....core.paths import BrainPaths, load_active_brain
from ....db.connection import get_connection
from ....services import ingest_service


def _brain() -> BrainPaths:
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


def _ingest_one(
    file: str,
    paths: BrainPaths,
    cfg: object,
    conn: object,
    *,
    force: bool = False,
) -> bool:
    """Ingest a single file. Returns True on success, False on failure.

    Failures are reported to stderr but do not raise, so a batch keeps going.
    An already-processed source is skipped (not a failure).
    """
    direct = Path(file)
    target = direct if direct.is_file() else (paths.root / file)
    if not target.is_file():
        typer.echo(f"[red]File not found: {file}[/red]", err=True)
        return False
    target = target.resolve()
    try:
        cr = ingest_service.ingest(target, paths, conn, cfg, force=force)  # type: ignore[arg-type]
    except SourceAlreadyProcessedError as exc:
        typer.echo(f"[yellow]Skipped (already processed):[/yellow] {esc(file)} — {exc} "
                   "Pass --force to re-ingest.")
        return True
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Ingestion failed for {file}: {exc}[/red]", err=True)
        return False
    typer.echo(f"[green]Source processed[/green] {esc(file)} (model: {cfg.model}).")  # type: ignore[attr-defined]
    for c in cr.changes:
        mark = "+" if c.operation == "create" else "~"
        typer.echo(f"  {mark} {esc(c.path)} ({c.operation})")
    if cr.files_changed == 0:
        typer.echo(
            f"[yellow]Warning: the model did not write any pages[/yellow] "
            f"(empty CR {cr.id}). Small models often fail at this — "
            f"use a model with good tool calling support."
        )
        return True
    typer.echo(f"Change request created: [bold]{cr.id}[/bold] ({cr.files_changed} files)")
    typer.echo(f"Review with:  wiki review {cr.id}")
    return True


def ingest(
    files: list[str] = typer.Argument(..., help="Source file(s) to ingest."),  # noqa: B008
    force: bool = typer.Option(  # noqa: B008
        False, "--force", "-f", help="Re-ingest even if the content was already processed."
    ),
) -> None:
    """Read one or more sources with the LLM and create change requests.

    Does not write to the wiki. Accepts paths within the brain
    (e.g. raw/articles/x.md), system files, or shell globs (e.g. raw/*.md).
    A failure on one file does not abort the rest; the command exits non-zero
    if any file failed. Already-processed sources are skipped unless --force.
    """
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    ok = 0
    failed = 0
    try:
        for file in files:
            if _ingest_one(file, paths, cfg, conn, force=force):
                ok += 1
            else:
                failed += 1
    finally:
        conn.close()
    if len(files) > 1 or failed:
        typer.echo(f"\nDone: {ok} ok, {failed} failed.")
    if failed:
        raise typer.Exit(code=1)