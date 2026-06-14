"""Ingest command: read a source with the LLM and create a change request."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape as esc

from ....core.config import load_config
from ....core.errors import NotFoundError, SourceAlreadyProcessedError
from ....core.models import ChangeRequest
from ....core.paths import BrainPaths, load_active_brain
from ....db.connection import get_connection
from ....services import ingest_service
from .._errors import handle_errors


def _brain() -> BrainPaths:
    return load_active_brain()


def _resolve(file: str, paths: BrainPaths) -> Path:
    direct = Path(file)
    target = direct if direct.is_file() else (paths.root / file)
    if not target.is_file():
        raise NotFoundError(f"File not found: {file}")
    return target.resolve()


def _report(file: str, cfg: object, cr: ChangeRequest) -> None:
    """Print the human result of one successful ingest."""
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
        return
    typer.echo(f"Change request created: [bold]{cr.id}[/bold] ({cr.files_changed} files)")
    typer.echo(f"Review with:  wiki review {cr.id}")


def _ingest_one(
    file: str,
    paths: BrainPaths,
    cfg: object,
    conn: object,
    *,
    force: bool = False,
) -> bool:
    """Ingest a single file inside a batch. Returns True on success/skip.

    Failures are reported to stderr but do not raise, so a batch keeps going.
    An already-processed source is skipped (not a failure).
    """
    try:
        target = _resolve(file, paths)
        cr = ingest_service.ingest(target, paths, conn, cfg, force=force)  # type: ignore[arg-type]
    except SourceAlreadyProcessedError as exc:
        typer.echo(
            f"[yellow]Skipped (already processed):[/yellow] {esc(file)} — {exc} "
            "Pass --force to re-ingest."
        )
        return True
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Ingestion failed for {file}: {exc}[/red]", err=True)
        return False
    _report(file, cfg, cr)
    return True


@handle_errors
def ingest(
    files: list[str] = typer.Argument(..., help="Source file(s) to ingest."),  # noqa: B008
    force: bool = typer.Option(  # noqa: B008
        False, "--force", "-f", help="Re-ingest even if the content was already processed."
    ),
    as_json: bool = typer.Option(  # noqa: B008
        False, "--json", help="Emit a JSON error envelope on stderr when the command fails."
    ),
) -> None:
    """Read one or more sources with the LLM and create change requests.

    Does not write to the wiki. Accepts paths within the brain
    (e.g. raw/articles/x.md), system files, or shell globs (e.g. raw/*.md).

    With a single source, typed failures map to standard exit codes (#198): a
    missing file is exit 3, an already-processed source is exit 4 (re-run with
    --force). With multiple sources the batch is resilient — a failure on one
    file does not abort the rest and the command exits non-zero if any failed.
    """
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        if len(files) == 1:
            # Single source: let typed errors propagate to the central handler.
            file = files[0]
            target = _resolve(file, paths)
            try:
                cr = ingest_service.ingest(target, paths, conn, cfg, force=force)
            except SourceAlreadyProcessedError as exc:
                raise SourceAlreadyProcessedError(
                    f"{exc} Re-run with --force to ingest anyway."
                ) from None
            _report(file, cfg, cr)
            return
        ok = failed = 0
        for file in files:
            if _ingest_one(file, paths, cfg, conn, force=force):
                ok += 1
            else:
                failed += 1
    finally:
        conn.close()
    typer.echo(f"\nDone: {ok} ok, {failed} failed.")
    if failed:
        raise typer.Exit(code=1)
