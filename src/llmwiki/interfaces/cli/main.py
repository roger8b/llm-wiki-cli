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
    ingest,
    index,
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
    source_app,
)
from .commands.brain import _create_brain_impl

app = typer.Typer(
    help="wiki — local-first knowledge base maintained by an LLM.",
    no_args_is_help=True,
    add_completion=False,
)

# Register sub-apps for nested commands.
app.add_typer(source_app, name="source")
app.add_typer(page_app, name="page")
app.add_typer(brain_app, name="brain")


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"llm-wiki {__version__}")


@app.command()
def init(
    path: str = typer.Argument("brain", help="Directory of the brain to create."),
    name: str | None = typer.Option(None, help="Name (default: folder name)."),
    no_git: bool = typer.Option(False, "--no-git", help="Do not run git init."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing brain."),
) -> None:
    """[DEPRECATED] Alias of 'wiki brain create'. Use 'wiki brain create'."""
    typer.echo("[yellow]'wiki init' is deprecated — use 'wiki brain create'.[/yellow]")
    _create_brain_impl(path, name, git=not no_git, force=force)


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