"""Brain registry subcommands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ....core.errors import WikiError
from ....services import scaffold_service

brain_app = typer.Typer(
    help="Manage brains (registry shared with app/MCP).",
    no_args_is_help=True,
)


def _resolve_brain_ref(ref: str):
    """Find a registered brain by id, path or name."""
    from ....core import brains as reg

    found = reg.get_brain(ref)
    if found:
        return found
    candidate = Path(ref).expanduser()
    if candidate.exists():
        found = reg.get_brain_by_path(candidate)
        if found:
            return found
    return next((b for b in reg.list_brains() if b.name == ref), None)


def _create_brain_impl(path: str, name: str | None, *, git: bool, force: bool) -> None:
    """Scaffold + register + activate a brain."""
    from ....core import brains as reg

    try:
        paths = scaffold_service.init_brain(
            Path(path).expanduser(), git=git, force=force
        )
    except WikiError as exc:
        raise typer.Exit(code=1) from exc
    b = reg.get_brain_by_path(paths.root)
    if b and name and b.name != name:
        reg.update_brain(b.id, {"name": name})
        b = reg.get_brain(b.id)
    typer.echo(f"[green]Created + active:[/green] {b.name if b else paths.root}  {paths.root}")


@brain_app.command("list")
def brain_list() -> None:
    """List registered brains (✓ = active, ⚠ = folder missing)."""
    from ....core import brains as reg

    brains = reg.list_brains()
    if not brains:
        typer.echo("No brains registered. Use 'wiki brain create <path>'.")
        return
    active = reg.get_active_brain()
    table = Table(show_header=True, header_style="bold")
    table.add_column("")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("ID")
    for b in brains:
        mark = "✓" if active and b.id == active.id else ""
        if not reg.is_brain_dir(Path(b.path)):
            mark = "⚠"
        table.add_row(mark, b.name, b.path, b.id[:8])
    Console(file=sys.stdout).print(table)


@brain_app.command("current")
def brain_current() -> None:
    """Show the active brain."""
    from ....core import brains as reg

    active = reg.get_active_brain()
    if not active:
        typer.echo("No active brain.")
        return
    typer.echo(f"[green]{active.name}[/green]  {active.path}  ({active.id[:8]})")


@brain_app.command("use")
def brain_use(ref: str = typer.Argument(..., help="Brain name, ID, or path.")) -> None:
    """Set the active brain (shared with app/MCP)."""
    from ....core import brains as reg

    b = _resolve_brain_ref(ref)
    if not b:
        raise typer.Exit(code=1)
    reg.set_active_brain(b.id)
    typer.echo(f"[green]Active:[/green] {b.name}  {b.path}")


@brain_app.command("add")
def brain_add(
    path: str = typer.Argument(..., help="Path to an existing brain."),
    name: str | None = typer.Option(None, help="Name (default: folder name)."),
) -> None:
    """Register an existing brain (does not create the directory structure)."""
    from ....core import brains as reg

    try:
        b = reg.add_brain(
            name or Path(path).expanduser().resolve().name,
            str(Path(path).expanduser().resolve()),
            activate=True,
        )
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"[green]Registered + active:[/green] {b.name}  {b.path}")


@brain_app.command("create")
def brain_create(
    path: str = typer.Argument(..., help="Path of the new brain to create."),
    name: str | None = typer.Option(None, help="Name (default: folder name)."),
    no_git: bool = typer.Option(False, "--no-git", help="Do not run git init."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing brain."),
) -> None:
    """Create (scaffold) a new brain, register, and activate it."""
    _create_brain_impl(path, name, git=not no_git, force=force)


@brain_app.command("rm")
def brain_rm(ref: str = typer.Argument(..., help="Name, ID, or path.")) -> None:
    """Remove a brain from the registry (does not delete the brain files)."""
    from ....core import brains as reg

    b = _resolve_brain_ref(ref)
    if not b:
        typer.echo(f"[red]Brain not found: {ref}[/red]", err=True)
        raise typer.Exit(code=1)
    try:
        reg.remove_brain(b.id)
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"[yellow]Removed from registry:[/yellow] {b.name}")