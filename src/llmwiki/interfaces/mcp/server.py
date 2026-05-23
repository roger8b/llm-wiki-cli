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


def _apply(cr_id: str) -> str:
    paths = get_paths()
    conn = get_connection(paths.db_path)
    try:
        cr = change_request_service.apply(cr_id, paths, conn)
    except ValueError as exc:
        return f"Erro: {exc}"
    finally:
        conn.close()
    return f"Change request {cr.id} aplicado (status={cr.status})."


def _reject(cr_id: str) -> str:
    paths = get_paths()
    conn = get_connection(paths.db_path)
    try:
        change_request_service.reject(cr_id, conn)
    except ValueError as exc:
        return f"Erro: {exc}"
    finally:
        conn.close()
    return f"Change request {cr_id} rejeitado."


def _list_pages() -> str:
    from ...db.repo import PageRepo

    paths = get_paths()
    conn = get_connection(paths.db_path)
    try:
        pages = PageRepo(conn).list()
    finally:
        conn.close()
    if not pages:
        return "Nenhuma página."
    return "\n".join(f"{p.path} — {p.title} ({p.type.value})" for p in pages)


def _list_sources() -> str:
    from ...db.repo import SourceRepo
    from ...sources.manager import sync_sources

    paths = get_paths()
    conn = get_connection(paths.db_path)
    try:
        repo = SourceRepo(conn)
        sync_sources(paths, repo)
        sources = repo.list()
    finally:
        conn.close()
    if not sources:
        return "Nenhuma fonte."
    return "\n".join(f"{s.path} [{s.status.value}]" for s in sources)


def _maintain() -> str:
    from ...services import maintenance_service

    paths = get_paths()
    cfg = get_config()
    findings = lint_service.lint_structural(paths)
    if not findings:
        return "Nada a corrigir — lint limpo."
    conn = get_connection(paths.db_path)
    try:
        cr = maintenance_service.maintain(findings, paths, conn, cfg)
    finally:
        conn.close()
    if cr is None:
        return "Nenhuma correção proposta."
    return f"Change request {cr.id} criado com correções. Revise antes de aplicar."


# ── brain registry (compartilhada com app/CLI) ──
def _list_brains() -> str:
    from pathlib import Path

    from ...core import brains as reg

    active = reg.get_active_brain()
    out = []
    for b in reg.list_brains():
        mark = "✓" if active and b.id == active.id else " "
        valid = "" if reg.is_brain_dir(Path(b.path)) else " [missing]"
        out.append(f"{mark} {b.name} — {b.path}{valid} ({b.id[:8]})")
    return "\n".join(out) if out else "Nenhum brain registrado."


def _current_brain() -> str:
    from ...core import brains as reg

    active = reg.get_active_brain()
    return f"{active.name} — {active.path}" if active else "Nenhum brain ativo."


def _use_brain(ref: str) -> str:
    from pathlib import Path as _P

    from ...core import brains as reg

    target = reg.get_brain(ref) or reg.get_brain_by_path(_P(ref).expanduser())
    if target is None:
        target = next((b for b in reg.list_brains() if b.name == ref), None)
    if target is None:
        return f"Brain não encontrado: {ref}"
    reg.set_active_brain(target.id)
    return f"Brain ativo agora: {target.name} — {target.path}"


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

    @mcp.tool()
    def wiki_apply(cr_id: str) -> str:
        """Aplica um change request (escreve os arquivos + reindexa)."""
        return _apply(cr_id)

    @mcp.tool()
    def wiki_reject(cr_id: str) -> str:
        """Rejeita um change request pendente."""
        return _reject(cr_id)

    @mcp.tool()
    def wiki_list_pages() -> str:
        """Lista as páginas da wiki do brain ativo."""
        return _list_pages()

    @mcp.tool()
    def wiki_list_sources() -> str:
        """Lista as fontes (raw/) do brain ativo."""
        return _list_sources()

    @mcp.tool()
    def wiki_maintain() -> str:
        """Roda o lint e propõe correções como um change request."""
        return _maintain()

    @mcp.tool()
    def wiki_list_brains() -> str:
        """Lista os brains registrados (✓ = ativo)."""
        return _list_brains()

    @mcp.tool()
    def wiki_current_brain() -> str:
        """Mostra o brain ativo (compartilhado com app e CLI)."""
        return _current_brain()

    @mcp.tool()
    def wiki_use_brain(ref: str) -> str:
        """Troca o brain ativo (por nome, id ou path) — afeta app, CLI e MCP."""
        return _use_brain(ref)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
