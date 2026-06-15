"""Markdown/plain text extractor: reads the file as utf-8."""

from __future__ import annotations

from pathlib import Path

from .base import ExtractedSource


def extract(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_source(path: Path) -> ExtractedSource:
    """Read the file and derive a title from frontmatter or the first H1."""
    from ...core import frontmatter, markdown

    text = path.read_text(encoding="utf-8")
    title: str | None = None
    try:
        meta, body = frontmatter.parse(text)
    except Exception:  # noqa: BLE001
        meta, body = {}, text
    fm_title = meta.get("title") if meta else None
    if isinstance(fm_title, str) and fm_title.strip():
        title = fm_title.strip()
    else:
        title = markdown.extract_title(body)

    def _str(key: str) -> str | None:
        val = meta.get(key) if meta else None
        return val.strip() if isinstance(val, str) and val.strip() else None

    # Carry capture provenance (url/author/date) from frontmatter so web
    # sources ingested via #195 keep their origin in the page `sources` (#163).
    return ExtractedSource(
        text=text,
        title=title,
        author=_str("author"),
        date=_str("date"),
        url=_str("url"),
    )
