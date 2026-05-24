"""Registry of extractors: extension -> function returning plain text."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import markdown as _markdown

Extractor = Callable[[Path], str]

_REGISTRY: dict[str, Extractor] = {
    ".md": _markdown.extract,
    ".markdown": _markdown.extract,
    ".txt": _markdown.extract,
}


def extract_text(path: Path) -> str:
    """Extracts text from a source based on its extension.

    Unknown extensions fallback to the plain text extractor (reads as utf-8).
    """
    extractor = _REGISTRY.get(path.suffix.lower(), _markdown.extract)
    return extractor(path)


def source_type(path: Path) -> str:
    """Classifies the source by extension (used in the ``sources.type`` column)."""
    ext = path.suffix.lower()
    return {
        ".md": "md",
        ".markdown": "md",
        ".txt": "text",
        ".pdf": "pdf",
        ".html": "html",
    }.get(ext, "other")
