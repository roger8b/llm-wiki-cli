"""MCP server — expõe a wiki para agentes externos (Claude Code etc.).

A lógica fica em funções ``_*`` testáveis; os tools MCP são wrappers finos.
A raiz do brain vem de ``WIKI_BRAIN`` ou da descoberta a partir do cwd.
Rodar: ``python -m llmwiki.interfaces.mcp.server`` (transporte stdio).
"""

from __future__ import annotations

from typing import Any

from ...db.connection import get_connection
from ...search.service import hybrid_search
from ...services import change_request_service, lint_service
from ..api.deps import get_config, get_paths


def _search(query: str) -> str:
    paths = get_paths()
    conn = get_connection(paths.db_path)
    try:
        hits = hybrid_search(conn, query, limit=10)
    finally:
        conn.close()
    if not hits:
        return "Nenhuma página encontrada."
    return "\n".join(f"{h.path} — {h.title}" for h in hits)


def _get_page(path: str) -> str:
    paths = get_paths()
    target = paths.root / path
    if not target.is_file():
        return f"Página não encontrada: {path}"
    return target.read_text(encoding="utf-8")


def _lint() -> str:
    paths = get_paths()
    findings = lint_service.lint_structural(paths)
    if not findings:
        return "Lint OK — nenhum problema estrutural."
    return "\n".join(f"[{f.severity.value}] {f.kind}: {f.message}" for f in findings)


def _ask(question: str) -> str:
    from ...services import query_service

    paths = get_paths()
    cfg = get_config()
    conn = get_connection(paths.db_path)
    try:
        result, _ = query_service.ask(question, paths, conn, cfg, save=False)
    finally:
        conn.close()
    refs = "\n".join(f"- {c.page or c.source}" for c in result.citations)
    return f"{result.answer}\n\nFontes:\n{refs}" if refs else result.answer


def _ingest(path: str) -> str:
    from ...core.paths import resolve_input
    from ...services import ingest_service

    paths = get_paths()
    cfg = get_config()
    target = resolve_input(path, paths.root)
    if not target.is_file():
        return f"Arquivo não encontrado: {path}"
    conn = get_connection(paths.db_path)
    try:
        cr = ingest_service.ingest(target, paths, conn, cfg)
    finally:
        conn.close()
    return f"Change request {cr.id} criado ({cr.files_changed} arquivos). Revise antes de aplicar."


def _list_pending() -> str:
    paths = get_paths()
    conn = get_connection(paths.db_path)
    try:
        crs = change_request_service.list_crs(conn, status="pending_review")
    finally:
        conn.close()
    if not crs:
        return "Nenhum change request pendente."
    return "\n".join(f"{cr.id}: {cr.files_changed} arquivos — {cr.summary or ''}" for cr in crs)


def build_server() -> Any:
    """Constrói o FastMCP com os tools. Retorno é Any (FastMCP vem do extra opcional)."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("llm-wiki")

    @mcp.tool()
    def wiki_search(query: str) -> str:
        """Busca páginas da wiki por palavra-chave."""
        return _search(query)

    @mcp.tool()
    def wiki_get_page(path: str) -> str:
        """Retorna o conteúdo Markdown de uma página da wiki."""
        return _get_page(path)

    @mcp.tool()
    def wiki_lint() -> str:
        """Audita a saúde estrutural da wiki (links quebrados, órfãs, frontmatter)."""
        return _lint()

    @mcp.tool()
    def wiki_ask(question: str) -> str:
        """Responde uma pergunta usando a wiki como fonte primária (com citações)."""
        return _ask(question)

    @mcp.tool()
    def wiki_ingest(path: str) -> str:
        """Ingere uma fonte e cria um change request (não escreve a wiki direto)."""
        return _ingest(path)

    @mcp.tool()
    def wiki_pending_changes() -> str:
        """Lista os change requests pendentes de revisão."""
        return _list_pending()

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
