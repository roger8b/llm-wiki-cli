"""Typer CLI for llm-wiki.

Commands: init, source add/list, page create/open, index, search, lint, log.
Interfaces are thin wrappers: they catch domain errors and translate them into messages
+ exit code 1. They never leak stacktraces.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape as _esc
from rich.table import Table

from ... import __version__
from ...core.config import load_config
from ...core.errors import WikiError
from ...core.models import PageType, Severity
from ...core.paths import BrainPaths, load_active_brain, resolve_input
from ...db.connection import get_connection
from ...db.repo import PageFtsRepo, SourceRepo
from ...services import (
    change_request_service,
    index_service,
    lint_service,
    page_service,
    scaffold_service,
)
from ...sources.manager import add_source

app = typer.Typer(
    help="wiki — local-first knowledge base maintained by an LLM.",
    no_args_is_help=True,
    add_completion=False,
)
source_app = typer.Typer(help="Manage raw sources in raw/.", no_args_is_help=True)
page_app = typer.Typer(help="Manage wiki pages.", no_args_is_help=True)
brain_app = typer.Typer(
    help="Manage brains (registry shared with app/MCP).",
    no_args_is_help=True,
)
app.add_typer(source_app, name="source")
app.add_typer(page_app, name="page")
app.add_typer(brain_app, name="brain")

console = Console()
err_console = Console(stderr=True)


def _fail(message: str) -> None:
    err_console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _brain() -> BrainPaths:
    """Resolve the active brain from the shared registry (no cwd needed)."""
    try:
        return load_active_brain()
    except WikiError as exc:
        _fail(str(exc))
        raise  # unreachable; satisfies the type checker


def _activate_brain_path(path: str) -> None:
    """Create (if missing), register and activate a brain at ``path``."""
    from ...core import brains as reg

    root = Path(path).expanduser().resolve()
    if not (root / ".llmwiki").is_dir():
        scaffold_service.init_brain(root, git=False)  # scaffolds + registers + activates
    else:
        reg.register_or_get(root, activate=True)


def _resolve_brain_ref(ref: str):
    """Find a registered brain by id, path or name."""
    from ...core import brains as reg

    found = reg.get_brain(ref)
    if found:
        return found
    candidate = Path(ref).expanduser()
    if candidate.exists():
        found = reg.get_brain_by_path(candidate)
        if found:
            return found
    return next((b for b in reg.list_brains() if b.name == ref), None)


# ───────────────────────────────── brain registry commands
@brain_app.command("list")
def brain_list() -> None:
    """List registered brains (✓ = active, ⚠ = folder missing)."""
    from ...core import brains as reg

    brains = reg.list_brains()
    if not brains:
        console.print("No brains registered. Use 'wiki brain create <path>'.")
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
    console.print(table)


@brain_app.command("current")
def brain_current() -> None:
    """Show the active brain."""
    from ...core import brains as reg

    active = reg.get_active_brain()
    if not active:
        console.print("No active brain.")
        return
    console.print(f"[green]{active.name}[/green]  {active.path}  ({active.id[:8]})")


@brain_app.command("use")
def brain_use(ref: str = typer.Argument(..., help="Brain name, ID, or path.")) -> None:
    """Set the active brain (shared with app/MCP)."""
    from ...core import brains as reg

    b = _resolve_brain_ref(ref)
    if not b:
        _fail(f"Brain not found: {ref}")
        return
    reg.set_active_brain(b.id)
    console.print(f"[green]Active:[/green] {b.name}  {b.path}")


@brain_app.command("add")
def brain_add(
    path: str = typer.Argument(..., help="Path to an existing brain."),
    name: str | None = typer.Option(None, help="Name (default: folder name)."),
) -> None:
    """Register an existing brain (does not create the directory structure)."""
    from ...core import brains as reg

    try:
        b = reg.add_brain(name or Path(path).expanduser().resolve().name,
                          str(Path(path).expanduser().resolve()), activate=True)
    except WikiError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]Registered + active:[/green] {b.name}  {b.path}")


def _create_brain(path: str, name: str | None, *, git: bool, force: bool) -> None:
    """Scaffold + register + activate a brain, optionally renaming it.

    Shared by ``wiki brain create`` and the deprecated ``wiki init`` alias.
    """
    from ...core import brains as reg

    try:
        paths = scaffold_service.init_brain(
            Path(path).expanduser(), git=git, force=force
        )
    except WikiError as exc:
        _fail(str(exc))
        return
    b = reg.get_brain_by_path(paths.root)
    if b and name and b.name != name:
        reg.update_brain(b.id, {"name": name})
        b = reg.get_brain(b.id)
    console.print(f"[green]Created + active:[/green] {b.name if b else paths.root}  {paths.root}")


@brain_app.command("create")
def brain_create(
    path: str = typer.Argument(..., help="Path of the new brain to create."),
    name: str | None = typer.Option(None, help="Name (default: folder name)."),
    no_git: bool = typer.Option(False, "--no-git", help="Do not run git init."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing brain."),
) -> None:
    """Create (scaffold) a new brain, register, and activate it."""
    _create_brain(path, name, git=not no_git, force=force)


@brain_app.command("rm")
def brain_rm(ref: str = typer.Argument(..., help="Name, ID, or path.")) -> None:
    """Remove a brain from the registry (does not delete the brain files)."""
    from ...core import brains as reg

    b = _resolve_brain_ref(ref)
    if not b:
        _fail(f"Brain not found: {ref}")
        return
    try:
        reg.remove_brain(b.id)
    except WikiError as exc:
        _fail(str(exc))
        return
    console.print(f"[yellow]Removed from registry:[/yellow] {b.name}")


@app.command()
def version() -> None:
    """Show the version."""
    console.print(f"llm-wiki {__version__}")


@app.command()
def init(
    path: str = typer.Argument("brain", help="Directory of the brain to create."),
    name: str | None = typer.Option(None, help="Name (default: folder name)."),
    no_git: bool = typer.Option(False, "--no-git", help="Do not run git init."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing brain."),
) -> None:
    """[DEPRECATED] Alias of 'wiki brain create'. Use 'wiki brain create'."""
    console.print(
        "[yellow]'wiki init' is deprecated — use 'wiki brain create'.[/yellow]"
    )
    _create_brain(path, name, git=not no_git, force=force)


@source_app.command("add")
def source_add(file: str = typer.Argument(..., help="Source file.")) -> None:
    """Register a raw file in raw/."""
    paths = _brain()
    src = Path(file).resolve()
    if not src.is_file():
        _fail(f"File not found: {file}")
    conn = get_connection(paths.db_path)
    try:
        result = add_source(src, paths, SourceRepo(conn))
    finally:
        conn.close()
    if result.already_present:
        console.print(
            f"[yellow]Source already registered[/yellow] (matching hash): {result.source.path}"
        )
    else:
        console.print(
            f"[green]Source registered:[/green] {result.source.path} "
            f"({result.source.status.value})"
        )


@source_app.command("list")
def source_list() -> None:
    """List registered sources."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        sources = SourceRepo(conn).list()
    finally:
        conn.close()
    if not sources:
        console.print("[dim]No sources registered.[/dim]")
        return
    table = Table("Path", "Type", "Status", "Title")
    for s in sources:
        table.add_row(_esc(s.path), s.type, s.status.value, _esc(s.title or ""))
    console.print(table)


@page_app.command("create")
def page_create(
    title: str = typer.Argument(..., help="Page title."),
    type_: str = typer.Option("concept", "--type", "-t", help="Page type."),
) -> None:
    """Create a wiki page from the type template."""
    paths = _brain()
    try:
        page_type = PageType(type_)
    except ValueError:
        valid = ", ".join(t.value for t in PageType)
        _fail(f"Invalid type '{type_}'. Use one of: {valid}")
        return
    try:
        dest = page_service.create_page(title, page_type, paths)
    except WikiError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]Page created:[/green] {paths.relative(dest)}")


@page_app.command("open")
def page_open(path: str = typer.Argument(..., help="Page path.")) -> None:
    """Print the content of a page."""
    paths = _brain()
    try:
        target = resolve_input(path, paths.root)
    except WikiError as exc:
        _fail(str(exc))
        return
    if not target.is_file():
        _fail(f"Page not found: {path}")
    console.print(target.read_text(encoding="utf-8"), markup=False)


@app.command()
def index() -> None:
    """Rebuild metadata and regenerate wiki/index.md."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        report = index_service.reindex(paths, conn)
        index_service.rebuild_index_md(paths, conn)
    finally:
        conn.close()
    console.print(
        f"[green]Index updated:[/green] {report.pages_indexed} pages, "
        f"{report.links_indexed} links."
    )
    if report.skipped:
        console.print(
            f"[yellow]Skipped (invalid frontmatter):[/yellow] "
            f"{', '.join(report.skipped)}"
        )


@app.command()
def search(query: str = typer.Argument(..., help="Search query (FTS5).")) -> None:
    """Search pages by keyword (FTS5 index)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        results = PageFtsRepo(conn).search(query)
    finally:
        conn.close()
    if not results:
        console.print("[dim]No results found.[/dim]")
        return
    table = Table("Page", "Title")
    for path, title, _rank in results:
        table.add_row(_esc(path), _esc(title))
    console.print(table)


@app.command()
def lint(
    semantic: bool = typer.Option(
        False, "--all/--structural", help="--all includes semantic audit via LLM."
    ),
) -> None:
    """Audit the health of the wiki (structural; --all adds semantic via LLM)."""
    paths = _brain()
    if semantic:
        cfg = load_config(paths)
        try:
            findings = lint_service.lint_all(paths, cfg, semantic=True)
        except Exception as exc:  # noqa: BLE001
            _fail(f"Semantic lint failed: {exc}")
            return
    else:
        findings = lint_service.lint_structural(paths)
    if not findings:
        console.print("[green]Lint OK — no issues found.[/green]")
        return
    color = {Severity.info: "blue", Severity.warn: "yellow", Severity.error: "red"}
    for f in findings:
        console.print(
            f"[{color[f.severity]}]{f.severity.value.upper()}[/] "
            f"{_esc(f.kind)}: {_esc(f.message)}"
        )
    errors = sum(1 for f in findings if f.severity == Severity.error)
    if errors:
        raise typer.Exit(code=1)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question for the wiki."),
    save: bool = typer.Option(False, "--save", help="Save the answer as a page (creates CR)."),
) -> None:
    """Answer a question using the wiki as the primary source."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        from ...services import query_service

        result, cr = query_service.ask(question, paths, conn, cfg, save=save)
    except Exception as exc:  # noqa: BLE001
        _fail(f"Query failed: {exc}")
        return
    finally:
        conn.close()
    console.print(result.answer, markup=False)
    if result.citations:
        console.print("\n[dim]Sources:[/dim]")
        for i, c in enumerate(result.citations, 1):
            ref = c.page or c.source or "?"
            console.print(f"  [{i}] {_esc(ref)}")
    if cr is not None:
        console.print(
            f"\n[green]Answer saved as change request {cr.id}[/green] "
            f"— review with wiki review {cr.id}"
        )


@app.command()
def maintain(
    apply_now: bool = typer.Option(False, "--apply", help="Apply the maintenance CR directly."),
) -> None:
    """Detect issues (lint --all) and propose fixes as a change request."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        from ...services import maintenance_service

        findings = lint_service.lint_all(paths, cfg, semantic=True)
        cr = maintenance_service.maintain(findings, paths, conn, cfg)
        if cr is None:
            console.print("[green]Nothing to correct.[/green]")
            return
        console.print(
            f"[green]Maintenance CR created: {cr.id}[/green] "
            f"({cr.files_changed} files)"
        )
        if apply_now:
            change_request_service.apply(cr.id, paths, conn)
            console.print(f"[green]Applied {cr.id}.[/green]")
    except Exception as exc:  # noqa: BLE001
        _fail(f"Maintenance failed: {exc}")
        return
    finally:
        conn.close()


@app.command()
def log() -> None:
    """Print wiki/log.md."""
    paths = _brain()
    if not paths.log_path.is_file():
        _fail("log.md not found.")
    console.print(paths.log_path.read_text(encoding="utf-8"), markup=False)


def _print_diff(diff: str) -> None:
    from rich.syntax import Syntax

    if diff.strip():
        console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))
    else:
        console.print("[dim](no difference)[/dim]")


@app.command()
def ingest(file: str = typer.Argument(..., help="Source file to ingest.")) -> None:
    """Read a source with the LLM and create a change request (does not write to the wiki).

    Accepts a path within the brain (e.g. raw/articles/x.md) or any
    readable system file (read as source, without copying).
    """
    paths = _brain()
    direct = Path(file)
    target = direct if direct.is_file() else (paths.root / file)
    if not target.is_file():
        _fail(f"File not found: {file}")
    target = target.resolve()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        from ...services import ingest_service

        cr = ingest_service.ingest(target, paths, conn, cfg)
    except Exception as exc:  # noqa: BLE001
        _fail(f"Ingestion failed: {exc}")
        return
    finally:
        conn.close()
    console.print(f"[green]Source processed[/green] (model: {cfg.model}).")
    for c in cr.changes:
        mark = "+" if c.operation == "create" else "~"
        console.print(f"  {mark} {_esc(c.path)} ({c.operation})")
    if cr.files_changed == 0:
        console.print(
            f"[yellow]Warning: the model did not write any pages[/yellow] "
            f"(empty CR {cr.id}). Small models often fail at this — "
            f"use a model with good tool calling support (e.g., larger/cloud)."
        )
        return
    console.print(f"Change request created: [bold]{cr.id}[/bold] ({cr.files_changed} files)")
    console.print(f"Review with:  wiki review {cr.id}")


@app.command()
def review(cr_id: str = typer.Argument(None, help="CR ID. Empty = list pending.")) -> None:
    """Show the diffs of a change request, or list pending ones."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        if cr_id is None:
            crs = change_request_service.list_crs(conn, status="pending_review")
            if not crs:
                console.print("[dim]No pending change requests.[/dim]")
                return
            table = Table("CR", "Files", "Summary")
            for cr in crs:
                table.add_row(cr.id, str(cr.files_changed), _esc((cr.summary or "")[:60]))
            console.print(table)
            return
        cr = change_request_service.get(cr_id, conn)
        if cr is None:
            _fail(f"Change request not found: {cr_id}")
            return
        console.print(f"[bold]{cr.id}[/bold] — {cr.status} — {_esc(cr.summary or '')}")
        for c in cr.changes:
            console.print(f"\n[cyan]{_esc(c.operation)}: {_esc(c.path)}[/cyan]")
            _print_diff(c.diff)
    finally:
        conn.close()


@app.command()
def apply(
    cr_id: str = typer.Argument(..., help="Change request ID."),
    commit: bool = typer.Option(False, "--commit", help="Create a git commit when applying."),
) -> None:
    """Apply a change request: writes to the wiki, reindexes, and records to the log."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        cr = change_request_service.apply(cr_id, paths, conn, git_commit=commit)
    except ValueError as exc:
        _fail(str(exc))
        return
    finally:
        conn.close()
    console.print(f"[green]Applied {cr.id}[/green] ({cr.files_changed} files).")


@app.command()
def reject(cr_id: str = typer.Argument(..., help="Change request ID.")) -> None:
    """Reject a change request (keeps the diffs for auditing)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        change_request_service.reject(cr_id, conn)
    except ValueError as exc:
        _fail(str(exc))
        return
    finally:
        conn.close()
    console.print(f"[yellow]Rejected {cr_id}.[/yellow]")


@app.command()
def jobs() -> None:
    """List registered jobs (ingest/lint/query)."""
    from ...db.repo import JobRepo

    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        rows = JobRepo(conn).list()
    finally:
        conn.close()
    if not rows:
        console.print("[dim]No jobs found.[/dim]")
        return
    table = Table("ID", "Type", "Status", "Created", "Error")
    for r in rows:
        table.add_row(
            str(r["id"]), r["type"], r["status"], r["created_at"][:19],
            _esc((r["error"] or "")[:30]),
        )
    console.print(table)


@app.command()
def mcp(
    brain: str | None = typer.Option(
        None, help="Activate this brain (path) before starting; otherwise uses the active one."
    ),
) -> None:
    """Start the MCP server (stdio) exposing the wiki to external agents.

    Follows the active brain from the registry — the same as the app/CLI. Changing brains in
    any channel is reflected here on every tool call (no restart required).
    """
    if brain is not None:
        _activate_brain_path(brain)
    paths = _brain()  # resolve the active one (clean error if none)
    try:
        from ...interfaces.mcp.server import main as mcp_main
    except ImportError:
        _fail("MCP SDK not installed. Run: pip install -e '.[mcp]'")
        return
    console.print(f"[green]MCP server (stdio)[/green] — active brain: {paths.root}")
    mcp_main()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host."),
    port: int = typer.Option(8000, help="Port."),
    brain: str | None = typer.Option(
        None,
        help="Brain to serve (pin). Created if it doesn't exist. "
        "Without this, uses the active brain from the registry; if none exists, the UI shows "
        "onboarding and the user registers one.",
    ),
) -> None:
    """Start the API + UI (requires the 'api' extra).

    - ``--brain X`` activates brain X in the registry (creates/registers if needed).
      Since the registry is shared, this also changes the CLI/MCP brain.
    - Without ``--brain``: uses the active brain from the registry. If none is
      registered, the server starts and the UI handles it as first-run/onboarding.
    """
    from ...core import brains as brains_registry

    if brain is not None:
        _activate_brain_path(brain)
        console.print(f"[green]Active brain[/green] {Path(brain).expanduser().resolve()}")
    else:
        active = brains_registry.get_active_brain()
        if active:
            console.print(f"[green]Active brain[/green] {active.path}")
        else:
            console.print(
                "[yellow]No brains registered — the UI will open the onboarding flow.[/yellow]"
            )

    try:
        import uvicorn
    except ImportError:
        _fail("FastAPI/uvicorn not installed. Run: pip install -e '.[api]'")
        return
    console.print(f"[green]API at[/green] http://{host}:{port}")
    uvicorn.run("llmwiki.interfaces.api.main:app", host=host, port=port)


if __name__ == "__main__":
    app()
