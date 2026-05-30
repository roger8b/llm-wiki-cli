"""MCP server command."""

from __future__ import annotations

from pathlib import Path

import typer

from ....core.errors import WikiError
from ....core.paths import BrainPaths, load_active_brain
from ....services import scaffold_service


def _brain() -> BrainPaths:
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


def _activate_brain_path(path: str) -> None:
    """Create (if missing), register and activate a brain at ``path``."""
    from ....core import brains as reg

    root = Path(path).expanduser().resolve()
    if not (root / ".llmwiki").is_dir():
        scaffold_service.init_brain(root, git=False)
    else:
        reg.register_or_get(root, activate=True)


def mcp(
    brain: str | None = typer.Option(
        None, help="Activate this brain (path) before starting."
    ),
) -> None:
    """Start the MCP server (stdio) exposing the wiki to external agents.

    Follows the active brain from the registry — changing brains in any channel
    is reflected here on every tool call.
    """
    if brain is not None:
        _activate_brain_path(brain)
    paths = _brain()
    try:
        from ....interfaces.mcp.server import main as mcp_main
    except ImportError:
        typer.echo("[red]MCP SDK not installed. Run: pip install -e '.[mcp]'[/red]", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"[green]MCP server (stdio)[/green] — active brain: {paths.root}")
    mcp_main()