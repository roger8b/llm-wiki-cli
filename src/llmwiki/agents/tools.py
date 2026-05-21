"""Tools de domínio expostas aos agentes. Cada tool abre conexão curta própria
(evita problemas de thread-safety do SQLite entre o agente e a CLI)."""

from __future__ import annotations

from collections.abc import Callable

from ..core.paths import BrainPaths
from ..db.connection import get_connection
from ..db.repo import PageFtsRepo


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
