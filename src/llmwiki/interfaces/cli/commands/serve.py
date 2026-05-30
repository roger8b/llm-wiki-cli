"""Serve command: start the API + UI server."""

from __future__ import annotations

from pathlib import Path

import typer

from ....core import brains as brains_registry
from ....core.errors import WikiError
from ....core.paths import load_active_brain
from ....services import scaffold_service


def _brain():
    try:
        return load_active_brain()
    except WikiError as exc:
        typer.echo(f"[red]{exc}[/red]", err=True)
        raise typer.Exit(code=1) from None


def _activate_brain_path(path: str) -> None:
    """Register and activate a brain at ``path``.

    Creates the directory tree (scaffold) if it doesn't exist.
    If already registered, just activates it without re-registering.
    If registered under a different name, re-uses the existing registration.
    """
    from ....core import brains as reg

    root = Path(path).expanduser().resolve()
    if not (root / ".llmwiki").is_dir():
        scaffold_service.init_brain(root, git=False)
    else:
        # Check if already registered — avoid double-registration.
        existing = reg.get_brain_by_path(root)
        if existing:
            active = reg.get_active_brain()
            if active is None or active.id != existing.id:
                reg.set_active_brain(existing.id)
        else:
            reg.register_or_get(root, activate=True)


def serve(
    host: str = typer.Option("127.0.0.1", help="Host."),
    port: int = typer.Option(8000, help="Port."),
    brain: str | None = typer.Option(
        None,
        help="Brain to serve (pin). Created if it doesn't exist. "
        "Without this, uses the active brain from the registry.",
    ),
) -> None:
    """Start the API + UI (requires the 'api' extra)."""
    if brain is not None:
        _activate_brain_path(brain)
        typer.echo(f"[green]Active brain[/green] {Path(brain).expanduser().resolve()}")
    else:
        active = brains_registry.get_active_brain()
        if active:
            typer.echo(f"[green]Active brain[/green] {active.path}")
        else:
            typer.echo(
                "[yellow]No brains registered — the UI will open the onboarding flow.[/yellow]"
            )
    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "[red]FastAPI/uvicorn not installed. Run: pip install -e '.[api]'[/red]",
            err=True,
        )
        raise typer.Exit(code=1) from None
    typer.echo(f"[green]API at[/green] http://{host}:{port}")
    # Keep idle connections open well past typical user think-time. The desktop
    # WebView (WKWebView) reuses keep-alive connections and surfaces a reset stale
    # connection as "Load failed"; the default 5s closes them while the user is
    # e.g. reviewing a diff before clicking Apply.
    uvicorn.run(
        "llmwiki.interfaces.api.main:app",
        host=host,
        port=port,
        timeout_keep_alive=300,
    )