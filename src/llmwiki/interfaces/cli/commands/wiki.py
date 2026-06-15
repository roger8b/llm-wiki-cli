"""Core wiki commands: index, search, lint, ask, maintain, log."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.markup import escape as esc

from ....core.config import load_config
from ....core.errors import WikiError
from ....core.models import PageType, Severity
from ....core.paths import BrainPaths, load_active_brain
from ....db.connection import get_connection
from ....db.repo import PageRepo
from ....search.factory import build_semantic_backend
from ....search.service import hybrid_search, keyword_search
from ....services import (
    autolink_service,
    change_request_service,
    curator_service,
    index_service,
    lint_service,
    query_service,
)
from .._errors import handle_errors
from .._output import emit

console = Console()


def _brain() -> BrainPaths:
    return load_active_brain()


@handle_errors
def index() -> None:
    """Rebuild metadata and regenerate wiki/index.md."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        report = index_service.reindex(paths, conn)
        index_service.rebuild_index_md(paths, conn)
    finally:
        conn.close()
    typer.echo(
        f"[green]Index updated:[/green] {report.pages_indexed} pages, "
        f"{report.links_indexed} links."
    )
    if report.skipped:
        typer.echo(
            f"[yellow]Skipped (invalid frontmatter):[/yellow] "
            f"{', '.join(report.skipped)}"
        )


@handle_errors
def search(
    query: str = typer.Argument(..., help="Search query (FTS5 + semantic when configured)."),
    type_: str | None = typer.Option(
        None, "--type", "-t", help="Filter by page type (e.g. concept, decision)."
    ),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results (default 10)."),
    keyword_only: bool = typer.Option(
        False, "--keyword-only", help="Force FTS even when semantic search is configured."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Search pages with snippets and optional type/tag filters."""
    paths = _brain()
    # Validate --type early (exit 2: invalid usage), before touching the DB.
    if type_ is not None:
        try:
            type_ = PageType(type_).value
        except ValueError:
            valid = ", ".join(t.value for t in PageType)
            typer.echo(
                f"[red]Invalid type '{type_}'. Use one of: {valid}[/red]", err=True
            )
            raise typer.Exit(code=2) from None

    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        # Over-fetch so post-filtering by type/tag still returns up to `limit`.
        fetch = limit if (type_ is None and tag is None) else max(limit * 5, 50)
        embedder, store = (None, None) if keyword_only else build_semantic_backend(cfg, conn)
        if embedder is not None:
            hits = hybrid_search(conn, query, limit=fetch, embedder=embedder, store=store)
        else:
            hits = keyword_search(conn, query, limit=fetch)
        # Enrich + filter with type/tags from the page index.
        index = {p.path: p for p in PageRepo(conn).list()}
    finally:
        conn.close()

    results: list[dict[str, object]] = []
    for hit in hits:
        page = index.get(hit.path)
        ptype = page.type.value if page else None
        tags = list(page.tags) if page else []
        if type_ is not None and ptype != type_:
            continue
        if tag is not None and tag.strip().lower() not in [t.lower() for t in tags]:
            continue
        results.append(
            {
                "path": hit.path,
                "title": hit.title,
                "score": round(hit.score, 4),
                "source": hit.source,
                "snippet": hit.snippet,
                "type": ptype,
                "tags": tags,
            }
        )
        if len(results) >= limit:
            break

    payload = {"results": results}

    def human() -> None:
        if not results:
            typer.echo("[dim]No results found.[/dim]")
            return
        for r in results:
            title = esc(str(r["title"] or r["path"]))
            meta = f"[dim][{r['source']} {r['score']}][/dim]"
            console.print(f"{esc(str(r['path']))} — {title}  {meta}")
            snippet = r["snippet"]
            if snippet:
                snip = esc(str(snippet)).replace("«", "[yellow]").replace("»", "[/yellow]")
                console.print(f"    {snip}")

    emit(payload, as_json=as_json, human=human)


@handle_errors
def lint(
    semantic: bool = typer.Option(
        False, "--all/--structural", help="--all includes semantic audit via LLM."
    ),
    scope: str | None = typer.Option(
        None, "--scope", help="Restrict semantic batches to one type dir (e.g. concepts)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Audit the health of the wiki (structural; --all adds semantic via LLM)."""
    paths = _brain()
    batches: list[lint_service.Batch] = []
    skipped: list[lint_service.Batch] = []
    if semantic:
        cfg = load_config(paths)
        try:
            report = lint_service.lint_batched(paths, cfg, scope=scope)
        except WikiError:
            raise
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"[red]Semantic lint failed: {exc}[/red]", err=True)
            raise typer.Exit(code=1) from exc
        findings = report.findings
        batches = report.processed
        skipped = report.skipped
    else:
        findings = lint_service.lint_structural(paths)
    errors = sum(1 for f in findings if f.severity == Severity.error)
    payload = {
        "findings": findings,
        "batches": [{"name": b.name, "pages": b.pages} for b in batches],
        "skipped": [{"name": b.name, "pages": b.pages} for b in skipped],
    }

    def human() -> None:
        color = {Severity.info: "blue", Severity.warn: "yellow", Severity.error: "red"}
        for f in findings:
            typer.echo(
                f"[{color[f.severity]}]{f.severity.value.upper()}[/] "
                f"{esc(f.kind)}: {esc(f.message)}"
            )
        if not findings:
            typer.echo("[green]Lint OK — no issues found.[/green]")
        if semantic:
            covered = sum(len(b.pages) for b in batches)
            typer.echo(
                f"\n[dim]Batches: {len(batches)} processed "
                f"({covered} pages){f', {len(skipped)} deferred' if skipped else ''}.[/dim]"
            )
            for b in skipped:
                typer.echo(
                    f"[yellow]deferred[/] {esc(b.name)} "
                    f"({len(b.pages)} pages) — over token budget"
                )

    emit(payload, as_json=as_json, human=human)
    if errors:
        raise typer.Exit(code=1)


@handle_errors
def ask(
    question: str = typer.Argument(..., help="Question for the wiki."),
    save: bool = typer.Option(False, "--save", help="Save the answer as a page (creates CR)."),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Answer a question using the wiki as the primary source."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        result, cr = query_service.ask(question, paths, conn, cfg, save=save)
    except WikiError:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Query failed: {exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()
    payload = {
        "answer": result.answer,
        "citations": [c.model_dump(mode="json") for c in result.citations],
        "suggested_page": (
            result.suggested_page.model_dump(mode="json")
            if result.suggested_page is not None
            else None
        ),
        "change_request_id": cr.id if cr is not None else None,
    }

    def human() -> None:
        Console(file=sys.stdout).print(result.answer, markup=False)
        if result.citations:
            typer.echo("\n[dim]Sources:[/dim]")
            for i, c in enumerate(result.citations, 1):
                ref = c.page or c.source or "?"
                if c.invalid:
                    typer.echo(f"  [{i}] [yellow](!) {esc(ref)} — não resolve[/yellow]")
                else:
                    typer.echo(f"  [{i}] {esc(ref)}")
        if cr is not None:
            typer.echo(
                f"\n[green]Answer saved as change request {cr.id}[/green] "
                f"— review with wiki review {cr.id}"
            )

    emit(payload, as_json=as_json, human=human)


@handle_errors
def maintain(
    apply_now: bool = typer.Option(False, "--apply", help="Apply the maintenance CR directly."),
) -> None:
    """Detect issues (lint --all) and propose fixes as a change request."""
    from ....services import maintenance_service

    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        findings = lint_service.lint_all(paths, cfg, semantic=True)
        cr = maintenance_service.maintain(findings, paths, conn, cfg)
        if cr is None:
            typer.echo("[green]Nothing to correct.[/green]")
            return
        typer.echo(
            f"[green]Maintenance CR created: {cr.id}[/green] "
            f"({cr.files_changed} files)"
        )
        warns = cr.warnings or []
        unresolved = [w for w in warns if w.startswith("unresolved:")]
        unverifiable = [w for w in warns if w.startswith("unverifiable:")]
        resolved = max(0, len(findings) - len(unresolved) - len(unverifiable))
        typer.echo(
            f"[dim]Verification: {resolved} resolved, "
            f"{len(unresolved)} unresolved, {len(unverifiable)} unverifiable.[/dim]"
        )
        for w in unresolved + unverifiable:
            typer.echo(f"  [yellow]{esc(w)}[/yellow]")
        if apply_now:
            change_request_service.apply(cr.id, paths, conn)
            typer.echo(f"[green]Applied {cr.id}.[/green]")
    except WikiError:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[red]Maintenance failed: {exc}[/red]", err=True)
        raise typer.Exit(code=1) from None
    finally:
        conn.close()


@handle_errors
def log(
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Print wiki/log.md."""
    paths = _brain()
    if not paths.log_path.is_file():
        if as_json:
            print('{"entries": []}')
            return
        typer.echo("[red]log.md not found.[/red]", err=True)
        raise typer.Exit(code=1)
    text = paths.log_path.read_text(encoding="utf-8")

    def human() -> None:
        Console(file=sys.stdout).print(text, markup=False)

    # Entries are the markdown blocks separated by blank lines; expose them as a
    # list while keeping the raw text for round-tripping.
    entries = [block.strip() for block in text.split("\n\n") if block.strip()]
    emit({"entries": entries, "raw": text}, as_json=as_json, human=human)

@handle_errors
def autolink(
    scope: str | None = typer.Option(
        None, "--scope", help="Restrict editing to one type dir (e.g. concepts)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List proposed links without creating a change request."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Wrap plain-text mentions of existing pages in [[wikilinks]] (deterministic, no LLM)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        result = autolink_service.propose_autolinks(
            paths, conn, scope=scope, dry_run=dry_run
        )
    finally:
        conn.close()

    if dry_run or isinstance(result, dict):
        report = result if isinstance(result, dict) else {"mentions": [], "pages": 0}
        payload = {"dry_run": dry_run, **report}

        def human_report() -> None:
            raw = report.get("mentions", [])
            mentions: list[dict[str, str]] = raw if isinstance(raw, list) else []
            if not mentions:
                typer.echo("[dim]No plain-text mentions to link.[/dim]")
                return
            for m in mentions:
                typer.echo(f"{esc(m['page'])}: {esc(m['snippet'])} → [[{esc(m['title'])}]]")
            typer.echo(
                f"\n[dim]{len(mentions)} mentions across {report.get('pages', 0)} pages.[/dim]"
            )

        emit(payload, as_json=as_json, human=human_report)
        return

    cr = result
    payload = {"change_request_id": cr.id, "files_changed": cr.files_changed}

    def human_cr() -> None:
        typer.echo(
            f"[green]Auto-link CR created: {cr.id}[/green] ({cr.files_changed} pages) "
            f"— review with wiki review {cr.id}"
        )

    emit(payload, as_json=as_json, human=human_cr)


@handle_errors
def curate(
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Run preventive maintenance (lint → verified fixes → auto-link) as CRs."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        report = curator_service.run_curation(paths, conn, cfg)
    finally:
        conn.close()
    payload = report.model_dump(mode="json")

    def human() -> None:
        typer.echo(
            f"Findings: {report.findings_total} "
            f"({report.findings_already_covered} already covered) — "
            f"resolved {report.resolved}, unresolved {report.unresolved}."
        )
        if report.autolink_mentions:
            typer.echo(f"Auto-link: {report.autolink_mentions} mentions proposed.")
        if report.change_requests:
            typer.echo(
                f"[green]Change requests:[/green] {', '.join(report.change_requests)} "
                "— review with wiki review"
            )
        else:
            typer.echo("[dim]Nothing to propose — the wiki is healthy.[/dim]")
        typer.echo(
            f"[dim]Tokens: {report.tokens_in} in / {report.tokens_out} out.[/dim]"
        )

    emit(payload, as_json=as_json, human=human)
