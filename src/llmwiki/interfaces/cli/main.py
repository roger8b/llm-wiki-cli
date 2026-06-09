"""Typer CLI for llm-wiki.

Commands: init, source add/list, page create/open, index, search, lint, log.
Interfaces are thin wrappers: they catch domain errors and translate them into messages
+ exit code 1.

Command split:
- commands/brain.py  — brain registry commands
- commands/source.py — source management
- commands/page.py  — page management
- commands/wiki.py  — index, search, lint, ask, maintain, log
- commands/review.py — review, apply, reject, jobs
- commands/ingest.py — ingest
- commands/mcp.py   — MCP server
- commands/serve.py  — API + UI server
"""

from __future__ import annotations

import typer

from ... import __version__
from .commands import (
    apply,
    ask,
    brain_app,
    index,
    ingest,
    jobs,
    lint,
    log,
    maintain,
    mcp,
    page_app,
    reject,
    review,
    search,
    serve,
    skills_app,
    source_app,
)

app = typer.Typer(
    help="wiki — local-first knowledge base maintained by an LLM.",
    no_args_is_help=True,
    add_completion=False,
)

# Register sub-apps for nested commands.
app.add_typer(source_app, name="source")
app.add_typer(page_app, name="page")
app.add_typer(brain_app, name="brain")
app.add_typer(skills_app, name="skills")


@app.callback()
def _main() -> None:
    """Configure logging once per CLI invocation (honours LLMWIKI_LOG_LEVEL)."""
    from ...core.logging import configure_logging

    configure_logging()


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"llm-wiki {__version__}")


@app.command()
def init(
    brain: str | None = typer.Option(
        None, "--brain", help="Brain the rules point to (default: the active brain)."
    ),
    agents: bool = typer.Option(False, "--agents", help="Only write AGENTS.md."),
    claude: bool = typer.Option(False, "--claude", help="Only write CLAUDE.md."),
    remove: bool = typer.Option(
        False, "--remove", help="Remove the managed rules block instead of writing it."
    ),
) -> None:
    """Write wiki-usage rules into this workspace's AGENTS.md / CLAUDE.md.

    Run inside a workspace (a code project). Teaches the agent to use the brain
    as a knowledge source (`wiki ask`) and to record durable knowledge
    (`wiki ingest`/CR). To CREATE a brain, use `wiki brain create`.
    """
    from pathlib import Path

    from ...core import brains as reg
    from ...services import rules_service

    cwd = Path.cwd()
    targets = []
    if agents:
        targets.append("AGENTS.md")
    if claude:
        targets.append("CLAUDE.md")
    if not targets:
        targets = list(rules_service.RULE_FILES)

    if remove:
        for fn in targets:
            removed = rules_service.remove_block(cwd / fn)
            typer.echo(f"{'removed block from' if removed else 'no block in'} {fn}")
        return

    active = reg.get_active_brain()
    brain_name = brain or (active.name if active else "your brain")
    if not active and not brain:
        typer.echo(
            "[yellow]No active brain — create one with 'wiki brain create'.[/yellow]"
        )
    block = rules_service.render_block(brain_name)
    for fn in targets:
        action = rules_service.upsert_block(cwd / fn, block)
        typer.echo(f"[green]{action}[/green] {fn}")


# Register top-level commands.
app.command()(index)
app.command()(search)
app.command()(lint)
app.command()(ask)
app.command()(maintain)
app.command()(log)
app.command()(ingest)
app.command()(review)
app.command()(apply)
app.command()(reject)
app.command()(jobs)
app.command()(mcp)
app.command()(serve)


if __name__ == "__main__":
    app()