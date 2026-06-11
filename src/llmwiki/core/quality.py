"""Per-page quality heuristic (issue #168).

Pure, deterministic, no LLM and no IO. Scores a page's Markdown content 0–100
from structural signals (body length, wikilinks, frontmatter completeness,
sections, sources) so a reviewer can prioritise the weakest pages in a change
request. Every lost criterion becomes a descriptive flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import frontmatter, markdown

# Required frontmatter fields for a "complete" page.
_REQUIRED_FM = ("title", "type", "tags", "sources", "updated_at", "confidence")

# Minimum body length, in words, for a substantial page.
_MIN_BODY_WORDS = 150

# Weights (sum = 100).
_W_BODY = 30
_W_LINKS = 25
_W_FRONTMATTER = 25
_W_SECTIONS = 10
_W_SOURCES = 10

_SECTION_RE = re.compile(r"^##\s+\S", re.MULTILINE)


@dataclass(frozen=True)
class QualityReport:
    score: int
    flags: list[str] = field(default_factory=list)


def _frontmatter_complete(meta: dict[str, object]) -> bool:
    for key in _REQUIRED_FM:
        value = meta.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
        if isinstance(value, list | dict) and not value:
            return False
    return True


def _has_sources(meta: dict[str, object]) -> bool:
    value = meta.get("sources")
    if value is None:
        return False
    if isinstance(value, list | str):
        return bool(value)
    return True


def assess_page(content: str, *, known_titles: set[str] | None = None) -> QualityReport:
    """Score ``content`` and list the criteria it fails.

    ``known_titles`` is a set of slugified page titles/stems; when provided, a
    wikilink only counts if it resolves to one of them.
    """
    try:
        meta, body = frontmatter.parse(content)
    except Exception:  # noqa: BLE001
        meta, body = {}, content

    score = 0
    flags: list[str] = []

    # Body length.
    if len(body.split()) >= _MIN_BODY_WORDS:
        score += _W_BODY
    else:
        flags.append("short_body")

    # Wikilinks (resolution-aware when known_titles is given).
    links = markdown.extract_wikilinks(body)
    if not links:
        flags.append("no_links")
    elif known_titles is not None and not any(
        markdown.slugify(t) in known_titles for t in links
    ):
        flags.append("unresolved_links")
    else:
        score += _W_LINKS

    # Frontmatter completeness.
    if _frontmatter_complete(meta):
        score += _W_FRONTMATTER
    else:
        flags.append("incomplete_frontmatter")

    # Sections (a ## heading beyond the title).
    if _SECTION_RE.search(body):
        score += _W_SECTIONS
    else:
        flags.append("no_sections")

    # Sources cited.
    if _has_sources(meta):
        score += _W_SOURCES
    else:
        flags.append("no_sources")

    return QualityReport(score=score, flags=flags)
