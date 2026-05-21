"""CLI Typer do llm-wiki (Fase 0).

Comandos: init, source add/list, page create/open, index, search, lint, log.
As interfaces são cascas finas: capturam erros de domínio e traduzem em mensagens
+ código de saída 1. Nunca deixam stacktrace vazar.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ... import __version__
from ...core.config import load_config
from ...core.errors import WikiError
from ...core.models import PageType, Severity
from ...core.paths import BrainPaths, load_brain, resolve_input
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
    help="llm-wiki — base de conhecimento local mantida por LLM.",
    no_args_is_help=True,
    add_completion=False,
)
source_app = typer.Typer(help="Gerencia fontes brutas em raw/.", no_args_is_help=True)
page_app = typer.Typer(help="Gerencia páginas da wiki.", no_args_is_help=True)
app.add_typer(source_app, name="source")
app.add_typer(page_app, name="page")

console = Console()
err_console = Console(stderr=True)


def _fail(message: str) -> None:
    err_console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _brain() -> BrainPaths:
    try:
        return load_brain()
    except WikiError as exc:
        _fail(str(exc))
        raise  # inalcançável; satisfaz o type checker


@app.command()
def version() -> None:
    """Mostra a versão."""
    console.print(f"llm-wiki {__version__}")


@app.command()
def init(
    path: str = typer.Argument("brain", help="Diretório do brain a criar."),
    no_git: bool = typer.Option(False, "--no-git", help="Não roda git init."),
    force: bool = typer.Option(False, "--force", help="Sobrescreve brain existente."),
) -> None:
    """Cria a estrutura de um novo brain."""
    try:
        paths = scaffold_service.init_brain(Path(path), git=not no_git, force=force)
    except WikiError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]Brain criado em[/green] {paths.root}")
    console.print("Próximo passo:  llmwiki source add <arquivo>")


@source_app.command("add")
def source_add(file: str = typer.Argument(..., help="Arquivo de fonte.")) -> None:
    """Registra um arquivo bruto em raw/."""
    paths = _brain()
    src = Path(file).resolve()
    if not src.is_file():
        _fail(f"Arquivo não encontrado: {file}")
    conn = get_connection(paths.db_path)
    try:
        result = add_source(src, paths, SourceRepo(conn))
    finally:
        conn.close()
    if result.already_present:
        console.print(
            f"[yellow]Fonte já registrada[/yellow] (hash igual): {result.source.path}"
        )
    else:
        console.print(
            f"[green]Fonte registrada:[/green] {result.source.path} "
            f"({result.source.status.value})"
        )


@source_app.command("list")
def source_list() -> None:
    """Lista as fontes registradas."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        sources = SourceRepo(conn).list()
    finally:
        conn.close()
    if not sources:
        console.print("[dim]Nenhuma fonte registrada.[/dim]")
        return
    table = Table("Path", "Tipo", "Status", "Título")
    for s in sources:
        table.add_row(s.path, s.type, s.status.value, s.title or "")
    console.print(table)


@page_app.command("create")
def page_create(
    title: str = typer.Argument(..., help="Título da página."),
    type_: str = typer.Option("concept", "--type", "-t", help="Tipo de página."),
) -> None:
    """Cria uma página da wiki a partir do template do tipo."""
    paths = _brain()
    try:
        page_type = PageType(type_)
    except ValueError:
        valid = ", ".join(t.value for t in PageType)
        _fail(f"Tipo inválido '{type_}'. Use um de: {valid}")
        return
    try:
        dest = page_service.create_page(title, page_type, paths)
    except WikiError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]Página criada:[/green] {paths.relative(dest)}")


@page_app.command("open")
def page_open(path: str = typer.Argument(..., help="Caminho da página.")) -> None:
    """Imprime o conteúdo de uma página."""
    paths = _brain()
    try:
        target = resolve_input(path, paths.root)
    except WikiError as exc:
        _fail(str(exc))
        return
    if not target.is_file():
        _fail(f"Página não encontrada: {path}")
    console.print(target.read_text(encoding="utf-8"))


@app.command()
def index() -> None:
    """Reconstrói os metadados e regenera wiki/index.md."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        report = index_service.reindex(paths, conn)
        index_service.rebuild_index_md(paths, conn)
    finally:
        conn.close()
    console.print(
        f"[green]Index atualizado:[/green] {report.pages_indexed} páginas, "
        f"{report.links_indexed} links."
    )
    if report.skipped:
        console.print(
            f"[yellow]Ignoradas (frontmatter inválido):[/yellow] "
            f"{', '.join(report.skipped)}"
        )


@app.command()
def search(query: str = typer.Argument(..., help="Termo de busca (FTS5).")) -> None:
    """Busca páginas por palavra-chave (índice FTS5)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        results = PageFtsRepo(conn).search(query)
    finally:
        conn.close()
    if not results:
        console.print("[dim]Nenhum resultado.[/dim]")
        return
    table = Table("Página", "Título")
    for path, title, _rank in results:
        table.add_row(path, title)
    console.print(table)


@app.command()
def lint(
    semantic: bool = typer.Option(
        False, "--all/--structural", help="--all inclui auditoria semântica via LLM."
    ),
) -> None:
    """Audita a saúde da wiki (estrutural; --all adiciona semântica via LLM)."""
    paths = _brain()
    if semantic:
        cfg = load_config(paths)
        try:
            findings = lint_service.lint_all(paths, cfg, semantic=True)
        except Exception as exc:  # noqa: BLE001
            _fail(f"Falha no lint semântico: {exc}")
            return
    else:
        findings = lint_service.lint_structural(paths)
    if not findings:
        console.print("[green]Lint OK — nenhum problema.[/green]")
        return
    color = {Severity.info: "blue", Severity.warn: "yellow", Severity.error: "red"}
    for f in findings:
        console.print(f"[{color[f.severity]}]{f.severity.value.upper()}[/] {f.kind}: {f.message}")
    errors = sum(1 for f in findings if f.severity == Severity.error)
    if errors:
        raise typer.Exit(code=1)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Pergunta para a wiki."),
    save: bool = typer.Option(False, "--save", help="Salvar a resposta como página (cria CR)."),
) -> None:
    """Responde uma pergunta usando a wiki como fonte primária."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        from ...services import query_service

        result, cr = query_service.ask(question, paths, conn, cfg, save=save)
    except Exception as exc:  # noqa: BLE001
        _fail(f"Falha na consulta: {exc}")
        return
    finally:
        conn.close()
    console.print(result.answer)
    if result.citations:
        console.print("\n[dim]Fontes:[/dim]")
        for i, c in enumerate(result.citations, 1):
            ref = c.page or c.source or "?"
            console.print(f"  [{i}] {ref}")
    if cr is not None:
        console.print(
            f"\n[green]Resposta salva como change request {cr.id}[/green] "
            f"— revise com llmwiki review {cr.id}"
        )


@app.command()
def maintain(
    apply_now: bool = typer.Option(False, "--apply", help="Aplica o CR de manutenção direto."),
) -> None:
    """Detecta problemas (lint --all) e propõe correções como change request."""
    paths = _brain()
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        from ...services import maintenance_service

        findings = lint_service.lint_all(paths, cfg, semantic=True)
        cr = maintenance_service.maintain(findings, paths, conn, cfg)
        if cr is None:
            console.print("[green]Nada a corrigir.[/green]")
            return
        console.print(
            f"[green]CR de manutenção criado: {cr.id}[/green] "
            f"({cr.files_changed} arquivos)"
        )
        if apply_now:
            change_request_service.apply(cr.id, paths, conn)
            console.print(f"[green]Aplicado {cr.id}.[/green]")
    except Exception as exc:  # noqa: BLE001
        _fail(f"Falha na manutenção: {exc}")
        return
    finally:
        conn.close()


@app.command()
def log() -> None:
    """Imprime wiki/log.md."""
    paths = _brain()
    if not paths.log_path.is_file():
        _fail("log.md não encontrado.")
    console.print(paths.log_path.read_text(encoding="utf-8"))


def _print_diff(diff: str) -> None:
    from rich.syntax import Syntax

    if diff.strip():
        console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))
    else:
        console.print("[dim](sem diferença)[/dim]")


@app.command()
def ingest(file: str = typer.Argument(..., help="Arquivo de fonte a ingerir.")) -> None:
    """Lê uma fonte com o LLM e cria um change request (não escreve a wiki)."""
    paths = _brain()
    try:
        target = resolve_input(file, paths.root)
    except WikiError as exc:
        _fail(str(exc))
        return
    if not target.is_file():
        _fail(f"Arquivo não encontrado: {file}")
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    try:
        from ...services import ingest_service

        cr = ingest_service.ingest(target, paths, conn, cfg)
    except Exception as exc:  # noqa: BLE001
        _fail(f"Falha na ingestão: {exc}")
        return
    finally:
        conn.close()
    console.print(f"[green]Fonte processada[/green] (modelo: {cfg.model}).")
    for c in cr.changes:
        mark = "+" if c.operation == "create" else "~"
        console.print(f"  {mark} {c.path} ({c.operation})")
    console.print(f"Change request criado: [bold]{cr.id}[/bold] ({cr.files_changed} arquivos)")
    console.print(f"Revise com:  llmwiki review {cr.id}")


@app.command()
def review(cr_id: str = typer.Argument(None, help="ID do CR. Vazio = lista pendentes.")) -> None:
    """Mostra os diffs de um change request, ou lista os pendentes."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        if cr_id is None:
            crs = change_request_service.list_crs(conn, status="pending_review")
            if not crs:
                console.print("[dim]Nenhum change request pendente.[/dim]")
                return
            table = Table("CR", "Arquivos", "Resumo")
            for cr in crs:
                table.add_row(cr.id, str(cr.files_changed), (cr.summary or "")[:60])
            console.print(table)
            return
        cr = change_request_service.get(cr_id, conn)
        if cr is None:
            _fail(f"Change request não encontrado: {cr_id}")
            return
        console.print(f"[bold]{cr.id}[/bold] — {cr.status} — {cr.summary or ''}")
        for c in cr.changes:
            console.print(f"\n[cyan]{c.operation}: {c.path}[/cyan]")
            _print_diff(c.diff)
    finally:
        conn.close()


@app.command()
def apply(
    cr_id: str = typer.Argument(..., help="ID do change request."),
    commit: bool = typer.Option(False, "--commit", help="Cria um commit git ao aplicar."),
) -> None:
    """Aplica um change request: escreve a wiki, reindexa e registra no log."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        cr = change_request_service.apply(cr_id, paths, conn, git_commit=commit)
    except ValueError as exc:
        _fail(str(exc))
        return
    finally:
        conn.close()
    console.print(f"[green]Aplicado {cr.id}[/green] ({cr.files_changed} arquivos).")


@app.command()
def reject(cr_id: str = typer.Argument(..., help="ID do change request.")) -> None:
    """Rejeita um change request (mantém os diffs para auditoria)."""
    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        change_request_service.reject(cr_id, conn)
    except ValueError as exc:
        _fail(str(exc))
        return
    finally:
        conn.close()
    console.print(f"[yellow]Rejeitado {cr_id}.[/yellow]")


@app.command()
def jobs() -> None:
    """Lista os jobs (ingest/lint/query) registrados."""
    from ...db.repo import JobRepo

    paths = _brain()
    conn = get_connection(paths.db_path)
    try:
        rows = JobRepo(conn).list()
    finally:
        conn.close()
    if not rows:
        console.print("[dim]Nenhum job.[/dim]")
        return
    table = Table("ID", "Tipo", "Status", "Criado", "Erro")
    for r in rows:
        table.add_row(
            str(r["id"]), r["type"], r["status"], r["created_at"][:19], (r["error"] or "")[:30]
        )
    console.print(table)


@app.command()
def mcp(
    host: str = typer.Option("127.0.0.1", help="Host (transporte http)."),
) -> None:
    """Sobe o MCP server (stdio) expondo a wiki para agentes externos."""
    import os

    paths = _brain()
    os.environ["WIKI_BRAIN"] = str(paths.root)
    try:
        from ...interfaces.mcp.server import main as mcp_main
    except ImportError:
        _fail("SDK MCP não instalado. Rode: pip install -e '.[mcp]'")
        return
    console.print(f"[green]MCP server (stdio)[/green] — brain: {paths.root}")
    mcp_main()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host."),
    port: int = typer.Option(8000, help="Porta."),
) -> None:
    """Sobe a API + UI de review (requer o extra 'api')."""
    import os

    paths = _brain()
    os.environ["WIKI_BRAIN"] = str(paths.root)
    try:
        import uvicorn
    except ImportError:
        _fail("FastAPI/uvicorn não instalados. Rode: pip install -e '.[api]'")
        return
    console.print(f"[green]API em[/green] http://{host}:{port}  (brain: {paths.root})")
    uvicorn.run("llmwiki.interfaces.api.main:app", host=host, port=port)


if __name__ == "__main__":
    app()
