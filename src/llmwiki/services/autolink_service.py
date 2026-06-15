"""Deterministic auto-linking of plain-text mentions to ``[[wikilinks]]`` (#44).

No LLM. Scans existing page bodies for the FIRST plain-text mention of another
page's title and proposes wrapping it in a wikilink, as one reviewable change
request. The matcher is the heart of the feature: it never touches frontmatter,
code (fenced or inline), URLs/markdown links, existing wikilinks, headings, or
the page's own title (self-link), and prefers the longest title on ambiguity.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..core import frontmatter, markdown
from ..core.errors import InvalidFrontmatterError
from ..core.models import ChangeRequest
from ..core.paths import BrainPaths
from ..llm_agents.backend import ChangeRequestBackend
from .change_request_service import create_from_changes

# Minimum title length to consider. 3 keeps common acronyms like "RAG" while
# still dropping 2-char noise ("ML", "AI") that would over-link.
_MIN_TITLE_CHARS = 3
_SPECIAL = {"index.md", "log.md"}

_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_FENCE_RE = re.compile(r"(?m)^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_WIKILINK_RE = re.compile(r"\[\[[^\]]*\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t].*$")


@dataclass
class Mention:
    page: str  # rel path of the page being edited
    title: str  # matched text, as it appears in the body
    target: str  # rel path of the page the link points to
    snippet: str  # short context around the match


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return ``(frontmatter_block, body)``; the block is empty when absent."""
    m = _FRONTMATTER_RE.match(text)
    if m:
        return text[: m.end()], text[m.end() :]
    return "", text


def _protected_spans(body: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for rx in (
        _FENCE_RE,
        _INLINE_CODE_RE,
        _WIKILINK_RE,
        _MD_LINK_RE,
        _URL_RE,
        _HEADING_RE,
    ):
        spans.extend((m.start(), m.end()) for m in rx.finditer(body))
    return spans


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s < end and start < e for s, e in spans)


def _snippet(body: str, start: int, end: int, *, width: int = 30) -> str:
    left = body[max(0, start - width) : start].replace("\n", " ")
    mid = body[start:end]
    right = body[end : end + width].replace("\n", " ")
    return f"…{left}«{mid}»{right}…".strip()


def find_mentions(
    body: str, titles: list[tuple[str, str]], *, page: str = ""
) -> list[Mention]:
    """Find the first linkable mention of each title in ``body``.

    ``titles`` is ``[(title_text, target_rel_path)]``. Longer titles are matched
    first so an ambiguous overlap (one title a prefix of another) prefers the
    longer one. Only the first non-protected, non-overlapping occurrence of each
    title is returned.
    """
    protected = _protected_spans(body)
    claimed: list[tuple[int, int]] = []
    mentions: list[Mention] = []
    # Longest title first; stable by title for determinism.
    for title, target in sorted(titles, key=lambda t: (-len(t[0]), t[0])):
        if target == page or len(title) < _MIN_TITLE_CHARS:
            continue
        pattern = re.compile(
            r"(?<![0-9A-Za-z_])" + re.escape(title) + r"(?![0-9A-Za-z_])",
            re.IGNORECASE,
        )
        for m in pattern.finditer(body):
            s, e = m.start(), m.end()
            if _overlaps(s, e, protected) or _overlaps(s, e, claimed):
                continue
            claimed.append((s, e))
            mentions.append(
                Mention(page=page, title=m.group(0), target=target, snippet=_snippet(body, s, e))
            )
            break
    return mentions


def _rewrite(body: str, titles: list[tuple[str, str]], *, page: str) -> tuple[str, list[Mention]]:
    mentions = find_mentions(body, titles, page=page)
    if not mentions:
        return body, []
    # Re-find spans to apply replacements right-to-left (positions stay valid).
    protected = _protected_spans(body)
    claimed: list[tuple[int, int]] = []
    edits: list[tuple[int, int, str]] = []
    used: set[str] = set()
    for title, target in sorted(titles, key=lambda t: (-len(t[0]), t[0])):
        if target == page or len(title) < _MIN_TITLE_CHARS or target in used:
            continue
        pattern = re.compile(
            r"(?<![0-9A-Za-z_])" + re.escape(title) + r"(?![0-9A-Za-z_])",
            re.IGNORECASE,
        )
        for m in pattern.finditer(body):
            s, e = m.start(), m.end()
            if _overlaps(s, e, protected) or _overlaps(s, e, claimed):
                continue
            claimed.append((s, e))
            edits.append((s, e, f"[[{m.group(0)}]]"))
            used.add(target)
            break
    for s, e, repl in sorted(edits, key=lambda x: x[0], reverse=True):
        body = body[:s] + repl + body[e:]
    return body, mentions


def _iter_pages(paths: BrainPaths, scope: str | None) -> list[Path]:
    wiki = paths.wiki
    if not wiki.is_dir():
        return []
    base = wiki / scope if scope else wiki
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.md") if p.name not in _SPECIAL)


def _page_title(rel: str, text: str) -> str:
    try:
        meta, body = frontmatter.parse(text)
    except InvalidFrontmatterError:
        meta, body = {}, text
    title = (meta.get("title") if meta else None) or markdown.extract_title(body) or Path(rel).stem
    return str(title)


def propose_autolinks(
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    scope: str | None = None,
    dry_run: bool = False,
) -> ChangeRequest | dict[str, object]:
    """Propose wikilinks for plain-text mentions across the wiki.

    Returns a ``ChangeRequest`` (or ``None`` wrapped as a report when nothing
    changes). With ``dry_run`` returns a ``{"mentions": [...]}`` report and
    creates no CR.
    """
    # Titles come from the whole wiki (scope only limits which pages are edited).
    all_files = {
        paths.relative(p): p.read_text(encoding="utf-8")
        for p in _iter_pages(paths, None)
    }
    titles: list[tuple[str, str]] = [
        (_page_title(rel, text), rel) for rel, text in all_files.items()
    ]

    backend = ChangeRequestBackend(paths.root)
    all_mentions: list[Mention] = []
    edited = 0
    for rel in (paths.relative(p) for p in _iter_pages(paths, scope)):
        text = all_files[rel]
        fm, body = _split_frontmatter(text)
        new_body, mentions = _rewrite(body, titles, page=rel)
        if not mentions or new_body == body:
            continue
        all_mentions.extend(mentions)
        edited += 1
        if not dry_run:
            backend.write(rel, fm + new_body)

    if dry_run:
        return {
            "mentions": [
                {"page": m.page, "title": m.title, "target": m.target, "snippet": m.snippet}
                for m in all_mentions
            ],
            "pages": edited,
        }

    changes = backend.collect_changes()
    if not changes:
        return {"mentions": [], "pages": 0}
    summary = f"Auto-link: {len(all_mentions)} menções em {edited} páginas"
    return create_from_changes(changes, summary, paths, conn)
