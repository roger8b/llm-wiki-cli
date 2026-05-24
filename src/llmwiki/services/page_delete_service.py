"""Deletion of wiki pages as reviewable change requests.

A page can be linked from other pages, so deleting it naively leaves broken
``[[links]]``. Deletion is therefore proposed as a change request (never applied
directly) and can optionally bundle edits that neutralize inbound links.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ..core import frontmatter, markdown
from ..core.diff import make_diff
from ..core.models import ChangeRequest, FileChange
from ..core.paths import BrainPaths
from .change_request_service import create_from_changes

_SPECIAL = {"index.md", "log.md"}
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")


def _index(paths: BrainPaths) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Build slug->rel, rel->body, rel->title maps over wiki pages."""
    slug_to_path: dict[str, str] = {}
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    if not paths.wiki.is_dir():
        return slug_to_path, bodies, titles
    for file in sorted(paths.wiki.rglob("*.md")):
        if file.name in _SPECIAL:
            continue
        rel = paths.relative(file)
        text = file.read_text(encoding="utf-8")
        try:
            meta, body = frontmatter.parse(text)
        except Exception:
            meta, body = {}, text
        title = (meta.get("title") if meta else None) or markdown.extract_title(body) or file.stem
        slug_to_path[markdown.slugify(str(title))] = rel
        slug_to_path[markdown.slugify(file.stem)] = rel
        bodies[rel] = text
        titles[rel] = str(title)
    return slug_to_path, bodies, titles


def find_backlinks(page_path: str, paths: BrainPaths) -> list[dict[str, str]]:
    """Pages whose ``[[link]]`` resolves to ``page_path`` (excluding the page itself)."""
    slug_to_path, bodies, titles = _index(paths)
    out: list[dict[str, str]] = []
    for rel, text in bodies.items():
        if rel == page_path:
            continue
        for target in markdown.extract_wikilinks(text):
            if slug_to_path.get(markdown.slugify(target)) == page_path:
                out.append({"path": rel, "title": titles.get(rel, rel)})
                break
    return out


def _deleted_slugs(page_path: str, body_text: str) -> set[str]:
    try:
        meta, body = frontmatter.parse(body_text)
    except Exception:
        meta, body = {}, body_text
    stem = Path(page_path).stem
    title = (meta.get("title") if meta else None) or markdown.extract_title(body) or stem
    return {markdown.slugify(str(title)), markdown.slugify(stem)}


def _unlink(text: str, deleted_slugs: set[str]) -> str:
    """Rewrite ``[[X]]`` / ``[[X|alias]]`` pointing at the deleted page to plain text."""

    def repl(m: re.Match[str]) -> str:
        target = m.group(1).strip()
        alias = (m.group(2) or "").strip()
        if markdown.slugify(target) in deleted_slugs:
            return alias or target
        return m.group(0)

    return _LINK_RE.sub(repl, text)


def delete_page(
    page_path: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    unlink_backlinks: bool = False,
) -> ChangeRequest:
    """Create a change request that deletes ``page_path`` (and optionally unlinks it)."""
    target = paths.root / page_path
    if not target.is_file():
        raise FileNotFoundError(page_path)

    old = target.read_text(encoding="utf-8")
    changes: list[FileChange] = [
        FileChange(
            path=page_path,
            operation="delete",
            new_content=None,
            diff=make_diff(old, "", page_path),
        )
    ]

    if unlink_backlinks:
        deleted_slugs = _deleted_slugs(page_path, old)
        for bl in find_backlinks(page_path, paths):
            rel = bl["path"]
            ref = paths.root / rel
            old_text = ref.read_text(encoding="utf-8")
            new_text = _unlink(old_text, deleted_slugs)
            if new_text != old_text:
                changes.append(
                    FileChange(
                        path=rel,
                        operation="update",
                        new_content=new_text,
                        diff=make_diff(old_text, new_text, rel),
                    )
                )

    return create_from_changes(changes, f"Delete page: {page_path}", paths, conn)
