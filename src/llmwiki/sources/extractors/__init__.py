"""Registry de extratores: extensão → função que devolve texto puro."""

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
    """Extrai texto de uma fonte conforme a extensão.

    Extensão desconhecida cai no extrator de texto puro (lê como utf-8).
    """
    extractor = _REGISTRY.get(path.suffix.lower(), _markdown.extract)
    return extractor(path)


def source_type(path: Path) -> str:
    """Classifica a fonte pela extensão (usado na coluna ``sources.type``)."""
    ext = path.suffix.lower()
    return {
        ".md": "md",
        ".markdown": "md",
        ".txt": "text",
        ".pdf": "pdf",
        ".html": "html",
    }.get(ext, "other")
