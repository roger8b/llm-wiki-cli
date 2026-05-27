"""`wiki skills` — install/manage agent skills shipped with the CLI."""

from __future__ import annotations

import typer

skills_app = typer.Typer(
    help="Install and manage agent skills (local-first).",
    no_args_is_help=True,
)


@skills_app.command("install")
def skills_install(
    scope: str = typer.Option("local", help="local (cwd) or global (~)."),
    agent: str = typer.Option("claude", help="Target agent adapter."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Install the shipped skills into the agent's skills directory."""
    from ....services import skills_service

    try:
        res = skills_service.install(scope=scope, agent=agent, force=force)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"[green]Installed[/green] {len(res['installed'])} skill(s) → {res['target']}")
    for name in res["installed"]:
        typer.echo(f"  · {name}")


@skills_app.command("list")
def skills_list(
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """List installed skills and their on-disk status."""
    from ....services import skills_service

    try:
        res = skills_service.list_installed(scope=scope, agent=agent)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    if not res["skills"]:
        typer.echo("[dim]No skills installed.[/dim]")
        return
    for s in res["skills"]:
        mark = "ok" if s["present"] else "MISSING"
        typer.echo(f"  · {s['name']} (v{s['version']}, {s['scope']}/{s['agent']}) [{mark}]")


@skills_app.command("doctor")
def skills_doctor(
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """Check installed skills for missing/modified/outdated state."""
    from ....services import skills_service

    try:
        res = skills_service.doctor(scope=scope, agent=agent)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    if res["ok"]:
        typer.echo("[green]All installed skills are healthy.[/green]")
    else:
        for issue in res["issues"]:
            typer.echo(
                f"[yellow]{issue['skill']}: {issue['issue']}[/yellow] — {issue['detail']}"
            )
    if res["available_not_installed"]:
        names = ", ".join(res["available_not_installed"])
        typer.echo(f"[dim]Available, not installed: {names}[/dim]")


@skills_app.command("update")
def skills_update(
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """Reinstall the shipped skills (refresh content to this CLI version)."""
    from ....services import skills_service

    try:
        res = skills_service.update(scope=scope, agent=agent)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"[green]Updated[/green] {len(res['installed'])} skill(s) → {res['target']}")


@skills_app.command("remove")
def skills_remove(
    name: str | None = typer.Argument(None, help="Skill to remove (omit for all)."),
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """Remove one skill (or all) and update the manifest."""
    from ....services import skills_service

    try:
        res = skills_service.remove(name, scope=scope, agent=agent)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    if res["removed"]:
        typer.echo(f"[yellow]Removed[/yellow]: {', '.join(res['removed'])}")
    else:
        typer.echo("[dim]Nothing to remove.[/dim]")
