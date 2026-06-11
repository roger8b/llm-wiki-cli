"""Registry of extractors: extension -> function returning text + metadata.

An extractor may return a plain ``str`` (legacy) or an ``ExtractedSource``
(text + provenance metadata, issue #163). ``extract()`` normalises both into an
``ExtractedSource``; ``extract_text()`` stays as a ``str`` wrapper for
backward compatibility.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import audio as _audio
from . import html as _html
from . import markdown as _markdown
from . import pdf as _pdf
from .base import ExtractedSource

# An extractor returns either plain text (legacy) or an ExtractedSource.
Extractor = Callable[[Path], "str | ExtractedSource"]

_REGISTRY: dict[str, Extractor] = {
    ".md": _markdown.extract_source,
    ".markdown": _markdown.extract_source,
    ".txt": _markdown.extract_source,
    ".pdf": _pdf.extract,
    ".html": _html.extract_source,
    ".htm": _html.extract_source,
    **{ext: _audio.extract for ext in _audio.AUDIO_EXTENSIONS},
}


def extract(path: Path) -> ExtractedSource:
    """Extract text + provenance metadata, normalising legacy ``str`` results."""
    extractor = _REGISTRY.get(path.suffix.lower(), _markdown.extract_source)
    result = extractor(path)
    if isinstance(result, ExtractedSource):
        return result
    return ExtractedSource(text=result)


def extract_text(path: Path) -> str:
    """Backward-compatible wrapper: just the text of the extracted source."""
    return extract(path).text


def source_type(path: Path) -> str:
    """Classifies the source by extension (used in the ``sources.type`` column)."""
    ext = path.suffix.lower()
    return {
        ".md": "md",
        ".markdown": "md",
        ".txt": "text",
        ".pdf": "pdf",
        ".html": "html",
        ".htm": "html",
        **{e: "audio" for e in _audio.AUDIO_EXTENSIONS},
    }.get(ext, "other")


__all__ = ["ExtractedSource", "extract", "extract_text", "source_type"]
