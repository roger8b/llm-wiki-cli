"""Index Builder: varre wiki/, popula metadados (pages, links, FTS) e regenera index.md.

Determinístico, sem LLM. Idempotente: limpa e reconstrói os índices a cada chamada.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from ..core import frontmatter, markdown
from ..core.errors import InvalidFrontmatterError
from ..core.models import Page, PageType
from ..core.paths import BrainPaths
from ..db.repo import LinkRepo, PageFtsRepo, PageRepo

# Páginas especiais que não entram como conteúdo indexável.
_SPECIAL = {"index.md", "log.md"}


class IndexReport(BaseModel):
    pages_indexed: int = 0
    links_indexed: int = 0
    skipped: list[str] = []


def _iter_wiki_files(wiki_dir: Path) -> list[Path]:
    if not wiki_dir.is_dir():
        return []
    return sorted(p for p in wiki_dir.rglob("*.md") if p.name not in _SPECIAL)


def reindex(paths: BrainPaths, conn: sqlite3.Connection) -> IndexReport:
    """Reconstrói wiki_pages, links e pages_fts a partir dos arquivos."""
    page_repo = PageRepo(conn)
    link_repo = LinkRepo(conn)
    fts_repo = PageFtsRepo(conn)

    page_repo.clear()
    link_repo.clear()
    fts_repo.clear()

    report = IndexReport()
    for file in _iter_wiki_files(paths.wiki):
        rel = paths.relative(file)
        text = file.read_text(encoding="utf-8")
        try:
            meta, body = frontmatter.parse(text)
        except InvalidFrontmatterError:
            report.skipped.append(rel)
            continue

        title = meta.get("title") or markdown.extract_title(body) or file.stem
        ptype = meta.get("type")
        try:
            page_type = PageType(ptype) if ptype else PageType.concept
        except ValueError:
            page_type = PageType.concept
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]

        page = Page(
            path=rel,
            title=str(title),
            type=page_type,
            summary=meta.get("summary"),
            tags=[str(t) for t in tags],
            last_updated_at=datetime.now(UTC),
            source_count=len(meta.get("sources") or []),
        )
        page_repo.upsert(page)
        fts_repo.add(rel, page.title, body, json.dumps(page.tags))
        report.pages_indexed += 1

        for target in markdown.extract_wikilinks(text):
            link_repo.add(rel, target)
            report.links_indexed += 1

    return report


def rebuild_index_md(paths: BrainPaths, conn: sqlite3.Connection) -> None:
    """Regenera wiki/index.md agrupando páginas por tipo."""
    pages = PageRepo(conn).list()
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        by_type.setdefault(page.type.value, []).append(page)

    lines = [
        "# Índice da Wiki",
        "",
        "> Gerado automaticamente por `llmwiki index`. Não editar à mão.",
        "",
    ]
    for ptype in sorted(by_type):
        lines.append(f"## {ptype}")
        lines.append("")
        for page in sorted(by_type[ptype], key=lambda p: p.title.lower()):
            lines.append(f"- [{page.title}]({page.path})")
        lines.append("")

    if not pages:
        lines.append("_Nenhuma página ainda._")
        lines.append("")

    paths.index_path.parent.mkdir(parents=True, exist_ok=True)
    paths.index_path.write_text("\n".join(lines), encoding="utf-8")
