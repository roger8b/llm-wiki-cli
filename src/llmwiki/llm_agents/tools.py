"""Tools de domínio expostas aos agentes. Cada tool abre conexão curta própria
(evita problemas de thread-safety do SQLite entre o agente e a CLI)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

from ..core import frontmatter, markdown
from ..core.config import WorkspaceConfig
from ..core.models import PageType
from ..core.paths import BrainPaths
from ..db.connection import get_connection
from ..db.repo import LinkRepo, PageRepo
from ..search.service import SearchHit, hybrid_search


def wiki_stats(paths: BrainPaths) -> str:
    """One-line summary of the wiki's current state, for the agent's message.

    Counts indexed pages per type via a short-lived connection (same pattern as
    the domain tools). An empty wiki returns an explicit hint so the agent knows
    every page it writes will be new.
    """
    conn = get_connection(paths.db_path)
    try:
        pages = PageRepo(conn).list()
    finally:
        conn.close()
    if not pages:
        return "wiki vazia — todas as páginas serão novas"
    counts: dict[str, int] = {}
    for page in pages:
        counts[page.type.value] = counts.get(page.type.value, 0) + 1
    ordered = [
        f"{t.value}: {counts[t.value]}" for t in PageType if counts.get(t.value)
    ]
    return f"{len(pages)} páginas — " + ", ".join(ordered)


# Max results and snippet shown by the search tool (#171).
_SEARCH_LIMIT = 10


def _hybrid_hits(
    conn: object, cfg: WorkspaceConfig, query: str, limit: int
) -> list[SearchHit]:
    """Run hybrid (keyword + semantic) search, or pure keyword when semantic off.

    The semantic backend is built lazily from ``cfg``; when no embedding model is
    configured (or sqlite-vec is unavailable) ``build_semantic_backend`` returns
    ``(None, None)`` and the result is identical to the old FTS-only search (#170).
    """
    import sqlite3

    from ..search.factory import build_semantic_backend

    assert isinstance(conn, sqlite3.Connection)
    embedder, store = build_semantic_backend(cfg, conn)
    return hybrid_search(conn, query, limit=limit, embedder=embedder, store=store)


def make_search_pages(paths: BrainPaths, cfg: WorkspaceConfig) -> Callable[[str], str]:
    def search_pages(query: str) -> str:
        """Busca páginas da wiki por SIGNIFICADO e por palavra-chave (busca
        híbrida): encontra a página certa mesmo sem o termo exato — busque pelo
        CONCEITO. Cada resultado traz 'path — título [origem:score]' e, na linha
        seguinte, um trecho « » para escolher a página sem abri-la."""
        conn = get_connection(paths.db_path)
        try:
            hits = _hybrid_hits(conn, cfg, query, _SEARCH_LIMIT)
        finally:
            conn.close()
        if not hits:
            return "Nenhuma página encontrada."
        lines: list[str] = []
        for hit in hits:
            lines.append(f"{hit.path} — {hit.title} [{hit.source}:{hit.score:.3f}]")
            if hit.snippet:
                lines.append(f"    «{hit.snippet}»")
        return "\n".join(lines)

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


def make_related_pages(paths: BrainPaths, cfg: WorkspaceConfig) -> Callable[[str], str]:
    def related_pages(title: str) -> str:
        """Para um TÍTULO proposto, lista páginas existentes relacionadas (por
        busca híbrida — significado + texto — e por tokens do slug em comum), com
        tipo e um link em comum quando houver. Chame ANTES de criar uma página
        para decidir entre editar uma existente ou linkar a vizinhança."""
        title = title.strip()
        if not title:
            return "Informe um título."
        title_tokens = {t for t in markdown.slugify(title).split("-") if len(t) >= 4}

        conn = get_connection(paths.db_path)
        try:
            pages = {p.path: p for p in PageRepo(conn).list()}
            candidates: set[str] = set()
            # (a) hybrid (semantic + keyword) search by the proposed title.
            for hit in _hybrid_hits(conn, cfg, title, 8):
                if hit.path in pages:
                    candidates.add(hit.path)
            # (b) pages whose slug (title or filename) shares a token with the title.
            for p in pages.values():
                page_tokens = set(markdown.slugify(p.title).split("-")) | set(
                    markdown.slugify(PurePosixPath(p.path).stem).split("-")
                )
                if title_tokens & page_tokens:
                    candidates.add(p.path)
            if not candidates:
                return "Nenhuma página relacionada encontrada — provavelmente é um conceito novo."
            link_repo = LinkRepo(conn)
            ordered = sorted(candidates)[:8]
            lines: list[str] = []
            for path in ordered:
                p = pages[path]
                # (c) a link this candidate shares with another candidate.
                common = next(
                    (
                        pages[t].title
                        for t in link_repo.outgoing(path)
                        if t in candidates and t != path
                    ),
                    None,
                )
                extra = f" [link em comum: {common}]" if common else ""
                lines.append(f"{path} — {p.title} ({p.type.value}){extra}")
        finally:
            conn.close()
        return "\n".join(lines)

    return related_pages


def domain_tools(paths: BrainPaths, cfg: WorkspaceConfig) -> list[Callable[[str], str]]:
    """All read-only domain tools exposed to the agents.

    ``cfg`` lets search-backed tools enable the semantic layer when an embedding
    model is configured (#170); otherwise they behave as pure FTS.
    """
    return [
        make_search_pages(paths, cfg),
        make_search_by_type(paths),
        make_get_backlinks(paths),
        make_read_metadata(paths),
        make_related_pages(paths, cfg),
    ]
