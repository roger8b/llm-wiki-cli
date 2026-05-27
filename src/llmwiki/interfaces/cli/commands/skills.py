"""`wiki skills` — install/manage agent skills from a central store."""

from __future__ import annotations

import typer

skills_app = typer.Typer(
    help="Install and manage agent skills (central store + symlink).",
    no_args_is_help=True,
)


@skills_app.command("install")
def skills_install(
    scope: str = typer.Option("local", help="local | global | both."),
    agent: str = typer.Option("claude", help="Target agent (pi, claude, gemini, cursor, codex…)."),
    method: str = typer.Option("symlink", help="symlink (default) | copy."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing links."),
) -> None:
    """Install the shipped skills into an agent's skills directory (from ~/.wiki/skills)."""
    from ....services import skills_service

    try:
        res = skills_service.install(agent=agent, scope=scope, method=method, force=force)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"[green]Store[/green] {res['store']} · method={res['method']} scope={res['scope']}")
    for r in res["results"]:
        typer.echo(f"  · {r['dest']} ({', '.join(r['agents'])}): {len(r['written'])} linked")


@skills_app.command("list")
def skills_list(
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """List installed skills across all agents/destinations."""
    from ....services import skills_service

    res = skills_service.list_installed()
    if not res["installs"]:
        typer.echo("[dim]No skills installed.[/dim]")
        return
    for inst in res["installs"]:
        agents = ", ".join(inst.get("agents", []))
        meta = f"{inst['scope']}/{inst['method']}, v{inst['version']}"
        typer.echo(f"  {inst['dest']} ({agents}, {meta})")
        for s in inst["skills_status"]:
            mark = "broken" if s["broken"] else ("ok" if s["present"] else "missing")
            link = "→" if s["symlink"] else " "
            typer.echo(f"      {link} {s['name']} [{mark}]")


@skills_app.command("doctor")
def skills_doctor(
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """Check installed skills for missing / broken-symlink / outdated state."""
    from ....services import skills_service

    res = skills_service.doctor()
    if res["ok"]:
        typer.echo("[green]All installed skills are healthy.[/green]")
        return
    for issue in res["issues"]:
        typer.echo(f"[yellow]{issue['dest']} · {issue['skill']}: {issue['issue']}[/yellow]")


@skills_app.command("update")
def skills_update(
    scope: str = typer.Option("local"),
    agent: str = typer.Option("claude"),
) -> None:
    """Refresh the central store and re-link every install."""
    from ....services import skills_service

    res = skills_service.update()
    typer.echo(f"[green]Updated[/green] store {res['store']} · {len(res['refreshed'])} install(s)")


@skills_app.command("remove")
def skills_remove(
    name: str | None = typer.Argument(None, help="Skill to remove (omit for all)."),
    scope: str | None = typer.Option(None, help="Limit to a scope (local|global|both)."),
    agent: str | None = typer.Option(None, help="Limit to an agent."),
) -> None:
    """Remove installed skill links (never deletes the central store)."""
    from ....services import skills_service

    try:
        res = skills_service.remove(name, agent=agent, scope=scope)
    except ValueError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    if res["removed"]:
        typer.echo(f"[yellow]Removed[/yellow] {len(res['removed'])} link(s).")
    else:
        typer.echo("[dim]Nothing to remove.[/dim]")
