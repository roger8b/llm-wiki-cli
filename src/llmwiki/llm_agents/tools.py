"""Tools de domínio expostas aos agentes. Cada tool abre conexão curta própria
(evita problemas de thread-safety do SQLite entre o agente e a CLI)."""

from __future__ import annotations

from collections.abc import Callable

from ..core import frontmatter
from ..core.paths import BrainPaths
from ..db.connection import get_connection
from ..db.repo import LinkRepo, PageFtsRepo, PageRepo


def make_search_pages(paths: BrainPaths) -> Callable[[str], str]:
    def search_pages(query: str) -> str:
        """Busca páginas da wiki por palavra-chave. Retorna 'path — título' por linha."""
        conn = get_connection(paths.db_path)
        try:
            results = PageFtsRepo(conn).search(query, limit=10)
        finally:
            conn.close()
        if not results:
            return "Nenhuma página encontrada."
        return "\n".join(f"{path} — {title}" for path, title, _ in results)

    return search_pages


def make_search_by_type(paths: BrainPaths) -> Callable[[str], str]:
    def search_by_type(page_type: str) -> str:
        """Lista páginas de um tipo (concept, entity, source_summary, synthesis,
        decision, project, research). Retorna 'path — título' por linha."""
        conn = get_connection(paths.db_path)
        try:
            pages = PageRepo(conn).by_type(page_type.strip())
        finally:
            conn.close()
        if not pages:
            return f"Nenhuma página do tipo '{page_type}'."
        return "\n".join(f"{p.path} — {p.title}" for p in pages)

    return search_by_type


def make_get_backlinks(paths: BrainPaths) -> Callable[[str], str]:
    def get_backlinks(page_path: str) -> str:
        """Lista páginas que apontam para `page_path` (links de entrada). Use antes
        de editar/renomear uma página para avaliar o impacto."""
        conn = get_connection(paths.db_path)
        try:
            sources = LinkRepo(conn).backlinks(page_path.strip())
        finally:
            conn.close()
        if not sources:
            return f"Nenhuma página aponta para '{page_path}'."
        return "\n".join(sources)

    return get_backlinks


def make_read_metadata(paths: BrainPaths) -> Callable[[str], str]:
    def read_metadata(page_path: str) -> str:
        """Lê apenas o frontmatter YAML de uma página (title, type, tags, sources,
        confidence…) sem carregar o corpo inteiro."""
        target = paths.root / page_path.strip().lstrip("/")
        if not target.is_file():
            return f"Arquivo não encontrado: {page_path}"
        try:
            meta, _ = frontmatter.parse(target.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return f"Frontmatter inválido em '{page_path}': {exc}"
        if not meta:
            return f"'{page_path}' não tem frontmatter."
        return "\n".join(f"{k}: {v}" for k, v in meta.items())

    return read_metadata


def domain_tools(paths: BrainPaths) -> list[Callable[[str], str]]:
    """All read-only domain tools exposed to the agents."""
    return [
        make_search_pages(paths),
        make_search_by_type(paths),
        make_get_backlinks(paths),
        make_read_metadata(paths),
    ]
