"""Semantic-ish duplicate detection for proposed pages (issue #167).

Deterministic, no embeddings (those arrive via #169/#170). Finds existing pages
that a newly-proposed title likely duplicates, by normalized-slug similarity
(exact or small edit distance) and a strong full-text hit. Used as a guardrail
in ``ChangeRequestBackend.write`` so the agent edits the existing page instead
of fragmenting a concept across near-duplicate files.
"""

from __future__ import annotations

import sqlite3

from . import markdown

# Max slug edit distance still considered "the same concept".
_MAX_SLUG_DISTANCE = 2


def _levenshtein(a: str, b: str) -> int:
    """Plain iterative Levenshtein distance (no dependency)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(
                    prev[j] + 1,
                    cur[j - 1] + 1,
                    prev[j - 1] + (ca != cb),
                )
            )
        prev = cur
    return prev[-1]


def find_similar_pages(
    title_or_slug: str, conn: sqlite3.Connection, *, limit: int = 3
) -> list[tuple[str, str, str]]:
    """Return up to ``limit`` existing pages similar to ``title_or_slug``.

    Each item is ``(path, title, reason)``. Reasons: ``"slug match"`` (identical
    or edit-distance ≤ 2) or ``"text match"`` (strong full-text hit covering
    every token of the title). TODO(#169): add embedding similarity.
    """
    from ..db.repo import PageFtsRepo, PageRepo

    target = markdown.slugify(title_or_slug)
    if not target:
        return []
    target_tokens = {t for t in target.split("-") if t}

    out: dict[str, tuple[str, str, str]] = {}

    # Match A: slug identical or within a small edit distance.
    for page in PageRepo(conn).list():
        for slug in (markdown.slugify(page.title), markdown.slugify(_stem(page.path))):
            if slug and (slug == target or _levenshtein(slug, target) <= _MAX_SLUG_DISTANCE):
                out.setdefault(page.path, (page.path, page.title, "slug match"))
                break

    # Match B: the strongest full-text hit whose indexed text covers EVERY token
    # of the proposed title (catches acronym/synonym pairs like
    # "Retrieval-Augmented Generation" ~ an existing "RAG" page).
    hits = PageFtsRepo(conn).search(title_or_slug, limit=limit + 2)
    for path, title, _rank in hits[:1]:  # only the top hit, to avoid false positives
        if path in out:
            continue
        row = conn.execute(
            "SELECT body FROM pages_fts WHERE path = ?", (path,)
        ).fetchone()
        body = (row["body"] if row is not None else "") or ""
        covered = set(markdown.slugify(f"{title} {body}").split("-"))
        if target_tokens and target_tokens <= covered:
            out.setdefault(path, (path, title, "text match"))

    return list(out.values())[:limit]


def _stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name
