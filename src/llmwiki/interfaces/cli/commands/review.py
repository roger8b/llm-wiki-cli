"""Change request commands: review, apply, reject, jobs."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.markup import escape as esc
from rich.syntax import Syntax
from rich.table import Table

from ....core.errors import WikiError
from ....core.paths import BrainPaths, load_active_brain
from ....db.connection import get_connection
from ....db.repo import JobRepo
from ....services import change_request_service
from .._output import emit

console = Console()


def _brain() -> BrainPaths:
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


def _print_diff(diff: str) -> None:
    if diff.strip():
        console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))
    else:
        console.print("[dim](no difference)[/dim]")


def review(
    cr_id: str = typer.Argument(None, help="CR ID. Empty = list pending."),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Show the diffs of a change request, or list pending ones."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        if cr_id is None:
            pending = change_request_service.list_crs(conn, status="pending_review")

            def _summary(cr: object) -> dict[str, object]:
                return {
                    "id": cr.id,
                    "status": cr.status,
                    "files_changed": cr.files_changed,
                    "summary": cr.summary,
                }

            payload = {"pending": [_summary(c) for c in pending]}

            def human_list() -> None:
                if not pending:
                    typer.echo("[dim]No pending change requests.[/dim]")
                    return
                table = Table("CR", "Files", "Summary")
                for cr in pending:
                    table.add_row(cr.id, str(cr.files_changed), esc((cr.summary or "")[:60]))
                Console(file=sys.stdout).print(table)

            emit(payload, as_json=as_json, human=human_list)
            return
        cr = change_request_service.get(cr_id, conn)
        if cr is None:
            if as_json:
                print(f'{{"error": {{"code": "not_found", "message": '
                      f'"Change request not found: {cr_id}"}}}}', file=sys.stderr)
                raise typer.Exit(code=1)
            typer.echo(f"[red]Change request not found: {cr_id}[/red]", err=True)
            raise typer.Exit(code=1)

        def human_detail() -> None:
            typer.echo(f"[bold]{cr.id}[/bold] — {cr.status} — {esc(cr.summary or '')}")
            for c in cr.changes:
                typer.echo(f"\n[cyan]{esc(c.operation)}: {esc(c.path)}[/cyan]")
                if c.quality_score is not None:
                    color = "green" if c.quality_score >= 80 else (
                        "yellow" if c.quality_score >= 60 else "red"
                    )
                    flags = f" — {esc(', '.join(c.quality_flags))}" if c.quality_flags else ""
                    typer.echo(f"[{color}]quality: {c.quality_score}/100[/{color}]{flags}")
                _print_diff(c.diff)

        emit(cr, as_json=as_json, human=human_detail)
    finally:
        conn.close()


def apply(
    cr_id: str = typer.Argument(..., help="Change request ID."),
    commit: bool = typer.Option(False, "--commit", help="Create a git commit when applying."),
    only: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--only",
        help="Apply only this path (repeatable); the rest are rejected (#184).",
    ),
) -> None:
    """Apply a change request: writes to the wiki, reindexes, and records to the log.

    With ``--only`` the named paths are applied and the remaining files are
    rejected — the CR settles in a single decision.
    """
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        cr = change_request_service.apply(
            cr_id, paths, conn, git_commit=commit, paths_filter=only or None
        )
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None
    finally:
        conn.close()
    if cr.rejected_paths:
        typer.echo(
            f"[green]Applied {cr.id}[/green] "
            f"({len(cr.applied_paths)} applied, {len(cr.rejected_paths)} rejected)."
        )
        for p in cr.applied_paths:
            typer.echo(f"  [green]applied[/green]: {p}")
        for p in cr.rejected_paths:
            typer.echo(f"  [yellow]rejected[/yellow]: {p}")
    else:
        typer.echo(f"[green]Applied {cr.id}[/green] ({cr.files_changed} files).")


def reject(cr_id: str = typer.Argument(..., help="Change request ID.")) -> None:
    """Reject a change request (keeps the diffs for auditing)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        change_request_service.reject(cr_id, conn)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None
    finally:
        conn.close()
    typer.echo(f"[yellow]Rejected {cr_id}.[/yellow]")


def jobs(
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """List registered jobs (ingest/lint/query)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        rows = JobRepo(conn).list()
    finally:
        conn.close()
    payload = {"jobs": [dict(r) for r in rows]}

    def human() -> None:
        if not rows:
            typer.echo("[dim]No jobs found.[/dim]")
            return
        table = Table("ID", "Type", "Status", "Created", "Error")
        for r in rows:
            table.add_row(
                str(r["id"]),
                r["type"],
                r["status"],
                r["created_at"][:19],
                esc((r["error"] or "")[:30]),
            )
        Console(file=sys.stdout).print(table)

    emit(payload, as_json=as_json, human=human)