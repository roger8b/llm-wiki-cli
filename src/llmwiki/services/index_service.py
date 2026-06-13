"""Index Builder: scans wiki/, populates metadata (pages, links, FTS), and regenerates index.md.

Deterministic, without LLM. Idempotent: clears and rebuilds indices on each call.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from ..core import frontmatter, markdown
from ..core.config import WorkspaceConfig
from ..core.errors import InvalidFrontmatterError
from ..core.misc import sha256
from ..core.models import Page, PageType
from ..core.paths import BrainPaths
from ..db.repo import LinkRepo, PageFtsRepo, PageRepo, TagRepo

logger = logging.getLogger("llmwiki.services.index")

# Special pages that are not indexed as content.
_SPECIAL = {"index.md", "log.md"}

# Pages shorter than this (chars) embed whole; longer ones split by H2 heading.
_EMBED_WHOLE_THRESHOLD = 8000


class IndexReport(BaseModel):
    pages_indexed: int = 0
    links_indexed: int = 0
    skipped: list[str] = []


def _iter_wiki_files(wiki_dir: Path) -> list[Path]:
    if not wiki_dir.is_dir():
        return []
    return sorted(p for p in wiki_dir.rglob("*.md") if p.name not in _SPECIAL)


def reindex(
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig | None = None,
) -> IndexReport:
    """Rebuilds wiki_pages, links, and pages_fts from the files.

    When ``cfg.embedding_model`` is set (and sqlite-vec available), incrementally
    refreshes semantic embeddings: only pages whose content hash changed are
    re-embedded, and removed pages are evicted (#169). Without it, behaviour is
    byte-identical to before.
    """
    page_repo = PageRepo(conn)
    link_repo = LinkRepo(conn)
    fts_repo = PageFtsRepo(conn)
    tag_repo = TagRepo(conn)

    page_repo.clear()
    link_repo.clear()
    fts_repo.clear()
    tag_repo.clear()

    report = IndexReport()
    bodies: dict[str, str] = {}  # rel -> body, for the semantic pass
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
        tag_repo.add(rel, page.tags)
        bodies[rel] = body
        report.pages_indexed += 1

        for target in markdown.extract_wikilinks(text):
            link_repo.add(rel, target)
            report.links_indexed += 1

    _reindex_embeddings(paths, conn, cfg, bodies)
    return report


def _chunk_for_embedding(body: str) -> list[str]:
    """Whole body when small, else split by ``## `` headings (#169)."""
    if len(body) <= _EMBED_WHOLE_THRESHOLD:
        return [body] if body.strip() else []
    chunks: list[str] = []
    current: list[str] = []
    for line in body.splitlines(keepends=True):
        if line.startswith("## ") and current:
            chunks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return [c for c in chunks if c.strip()]


def _reindex_embeddings(
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig | None,
    bodies: dict[str, str],
) -> None:
    """Refresh semantic embeddings for changed/removed pages, if configured."""
    if cfg is None:
        from ..core.config import load_config

        cfg = load_config(paths)
    if not cfg.embedding_model:
        return

    from ..search.factory import build_semantic_backend

    embedder, store = build_semantic_backend(cfg, conn)
    if embedder is None or store is None:
        return

    for path in store.indexed_paths() - bodies.keys():
        store.delete_page(path)  # page removed from disk

    for path, body in bodies.items():
        content_hash = sha256(body.encode("utf-8"))
        if store.page_hash(path) == content_hash:
            continue  # unchanged — skip re-embedding
        chunks = _chunk_for_embedding(body)
        if not chunks:
            store.delete_page(path)
            continue
        try:
            vectors = [embedder.embed(c) for c in chunks]
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding failed for %s, skipping semantic index: %s", path, exc)
            continue
        store.replace_page(path, vectors, content_hash)


def rebuild_index_md(paths: BrainPaths, conn: sqlite3.Connection) -> None:
    """Regenerates wiki/index.md grouping pages by type."""
    pages = PageRepo(conn).list()
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        by_type.setdefault(page.type.value, []).append(page)

    lines = [
        "# Wiki Index",
        "",
        "> Automatically generated by `llmwiki index`. Do not edit by hand.",
        "",
    ]
    for ptype in sorted(by_type):
        lines.append(f"## {ptype}")
        lines.append("")
        for page in sorted(by_type[ptype], key=lambda p: p.title.lower()):
            lines.append(f"- [{page.title}]({page.path})")
        lines.append("")

    if not pages:
        lines.append("_No pages yet._")
        lines.append("")

    paths.index_path.parent.mkdir(parents=True, exist_ok=True)
    paths.index_path.write_text("\n".join(lines), encoding="utf-8")
