"""Pure Markdown utilities: wikilinks, headings, slugs."""

from __future__ import annotations

import re
import unicodedata

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def extract_wikilinks(text: str) -> list[str]:
    """Returns targets of ``[[Link]]`` (supports ``[[Target|text]]``), without duplicates,
    preserving order. Ignores links within HTML comments (``<!-- ... -->``)."""
    text = _COMMENT_RE.sub("", text)
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.finditer(text):
        target = match.group(1).strip()
        if target:
            seen.setdefault(target, None)
    return list(seen)


def extract_title(text: str) -> str | None:
    """First H1 heading (``# Title``) of the body, or ``None``."""
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else None


def slugify(value: str) -> str:
    """Converts a title into an ASCII kebab-case slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _SLUG_STRIP_RE.sub("-", ascii_only).strip("-")
