"""Utilitários puros de Markdown: wikilinks, títulos, slugs."""

from __future__ import annotations

import re
import unicodedata

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def extract_wikilinks(text: str) -> list[str]:
    """Retorna os alvos de ``[[Link]]`` (suporta ``[[Alvo|texto]]``), sem duplicatas,
    preservando ordem. Ignora links dentro de comentários HTML (``<!-- ... -->``)."""
    text = _COMMENT_RE.sub("", text)
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.finditer(text):
        target = match.group(1).strip()
        if target:
            seen.setdefault(target, None)
    return list(seen)


def extract_title(text: str) -> str | None:
    """Primeiro heading H1 (``# Título``) do corpo, ou ``None``."""
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else None


def slugify(value: str) -> str:
    """Converte um título em slug kebab-case ascii."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _SLUG_STRIP_RE.sub("-", ascii_only).strip("-")
