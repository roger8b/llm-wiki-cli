"""`wiki skills` — install/manage agent skills from a central store."""

from __future__ import annotations

import sys

import typer

skills_app = typer.Typer(
    help="Install and manage agent skills (central store + symlink).",
    no_args_is_help=True,
)


def _interactive_pick() -> tuple[list[str], str, str, bool]:
    """Prompt for agents, scope, method, and overwrite. Returns the choices."""
    from ....core.agents import AGENTS, detect_installed_agents

    detected = set(detect_installed_agents())
    items = list(AGENTS.items())
    typer.echo("Agents (comma-separated numbers, or 'all'):")
    for i, (name, spec) in enumerate(items, 1):
        tag = " [green](detected)[/green]" if name in detected else ""
        typer.echo(f"  {i}. {spec.display}{tag}")
    default = ",".join(str(i) for i, (n, _) in enumerate(items, 1) if n in detected) or "2"
    raw = typer.prompt("Agents", default=default)
    if raw.strip().lower() == "all":
        agents = [n for n, _ in items]
    else:
        idxs = [int(x) for x in raw.replace(" ", "").split(",") if x.strip().isdigit()]
        agents = [items[i - 1][0] for i in idxs if 1 <= i <= len(items)]

    scope = typer.prompt("Scope (local/global/both)", default="local")
    method = typer.prompt("Method (symlink/copy)", default="symlink")
    force = typer.confirm("Overwrite existing skills?", default=False)
    return agents, scope, method, force


@skills_app.command("install")
def skills_install(
    scope: str | None = typer.Option(None, help="local | global | both."),
    agent: str | None = typer.Option(None, help="Target agent (pi, claude, gemini, cursor…)."),
    agents: str | None = typer.Option(None, help="Comma-separated agents."),
    method: str | None = typer.Option(None, help="symlink (default) | copy."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive (sensible defaults)."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing links."),
) -> None:
    """Install the shipped skills into agents' skills dirs (from ~/.wiki/skills).

    With no flags on a terminal, runs interactively (pick agents/scope/method).
    Pass --yes or any flag for non-interactive use.
    """
    from ....services import skills_service

    explicit = scope or agent or agents or method or yes
    agent_list: list[str] | None = None
    if agents:
        agent_list = [a.strip() for a in agents.split(",") if a.strip()]
    elif agent:
        agent_list = [agent]

    if not explicit and sys.stdin.isatty():
        agent_list, scope, method, force = _interactive_pick()
        if not agent_list:
            typer.echo("[yellow]No agents selected — nothing to do.[/yellow]")
            return

    try:
        res = skills_service.install(
            agents=agent_list,
            scope=scope or "local",
            method=method or "symlink",
            force=force,
        )
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
