"""HTML extractor: main-content extraction via trafilatura (optional ``[html]``).

Strips boilerplate (nav, scripts, footer) and returns the article body as
Markdown, so the agent's context isn't wasted on menus and chrome. Also exposes
``extract_metadata`` (title/author/date/url) for the source-metadata pipeline
(issue #163) to consume.
"""

from __future__ import annotations

from pathlib import Path

from ...core.errors import EmptyExtractionError, ExtractorUnavailableError
from .base import ExtractedSource


def _load_trafilatura() -> object:
    try:
        import trafilatura
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise ExtractorUnavailableError(
            "HTML support requires trafilatura. "
            "Install it with: pip install 'llm-wiki[html]'"
        ) from exc
    return trafilatura


def extract(path: Path) -> str:
    """Extract the main content of an HTML file as Markdown.

    Raises ``ExtractorUnavailableError`` if trafilatura is missing and
    ``EmptyExtractionError`` if no main content can be detected.
    """
    trafilatura = _load_trafilatura()
    html = path.read_text(encoding="utf-8", errors="replace")
    text: str | None = trafilatura.extract(  # type: ignore[attr-defined]
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )
    if not text or not text.strip():
        raise EmptyExtractionError(
            f"No main content detected in {path.name} "
            "(empty page, paywall, or JavaScript-rendered content)."
        )
    return text.strip()


def extract_metadata(path: Path) -> dict[str, str | None]:
    """Best-effort source metadata: title, author, date, url.

    Never raises for missing fields — absent values come back as ``None``.
    """
    trafilatura = _load_trafilatura()
    html = path.read_text(encoding="utf-8", errors="replace")
    meta = trafilatura.extract_metadata(html)  # type: ignore[attr-defined]
    if meta is None:
        return {"title": None, "author": None, "date": None, "url": None}
    return {
        "title": getattr(meta, "title", None),
        "author": getattr(meta, "author", None),
        "date": getattr(meta, "date", None),
        "url": getattr(meta, "url", None),
    }


def extract_source(path: Path) -> ExtractedSource:
    """Main-content text plus provenance metadata (issue #163)."""
    trafilatura = _load_trafilatura()
    html = path.read_text(encoding="utf-8", errors="replace")
    text: str | None = trafilatura.extract(  # type: ignore[attr-defined]
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )
    if not text or not text.strip():
        raise EmptyExtractionError(
            f"No main content detected in {path.name} "
            "(empty page, paywall, or JavaScript-rendered content)."
        )
    meta = trafilatura.extract_metadata(html)  # type: ignore[attr-defined]
    return ExtractedSource(
        text=text.strip(),
        title=getattr(meta, "title", None) if meta is not None else None,
        author=getattr(meta, "author", None) if meta is not None else None,
        date=getattr(meta, "date", None) if meta is not None else None,
        url=getattr(meta, "url", None) if meta is not None else None,
    )
