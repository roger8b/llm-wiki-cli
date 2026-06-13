"""Creation and manual editing of wiki pages (deterministic, no LLM)."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path
from typing import Any

from ..core.errors import PageExistsError
from ..core.markdown import slugify
from ..core.misc import today
from ..core.models import ChangeRequest, PageType
from ..core.paths import BrainPaths

_VALID_TYPES = {t.value for t in PageType}


class PageEditError(ValueError):
    """Invalid manual edit (HTTP 400)."""


class InvalidPageTypeError(PageEditError):
    """The frontmatter ``type`` is not a known PageType (HTTP 400)."""


class NoPageChangesError(PageEditError):
    """The edit is identical to what's on disk — nothing to propose (HTTP 409)."""

# Page type -> subdirectory in wiki/.
_DIR = {
    PageType.concept: "concepts",
    PageType.entity: "entities",
    PageType.source_summary: "research",
    PageType.synthesis: "synthesis",
    PageType.decision: "decisions",
    PageType.project: "projects",
    PageType.research: "research",
}


def _template(page_type: PageType) -> str:
    return (
        resources.files("llmwiki")
        .joinpath("templates", "page_templates", f"{page_type.value}.md")
        .read_text(encoding="utf-8")
    )


def create_page(
    title: str, page_type: PageType, paths: BrainPaths
) -> Path:
    """Creates a new page from the type template. Returns the created path."""
    slug = slugify(title)
    dest = paths.wiki / _DIR[page_type] / f"{slug}.md"
    if dest.exists():
        raise PageExistsError(f"Page already exists: {paths.relative(dest)}")

    content = _template(page_type).replace("{{title}}", title).replace("{{today}}", today())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def propose_edit(
    path: str,
    frontmatter_meta: dict[str, Any],
    body: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
) -> ChangeRequest:
    """Propose a manual page edit as a change request (#186) — no LLM, no direct write.

    Validates the frontmatter (``type`` must be a PageType, ``title`` required),
    stamps ``updated_at`` (backend's responsibility), serialises the page, and
    routes it through ``ChangeRequestBackend`` so it lands as a reviewable CR.
    Content identical to disk raises ``NoPageChangesError``.
    """
    from ..core import frontmatter
    from ..llm_agents.backend import ChangeRequestBackend
    from . import change_request_service

    norm = path.lstrip("/")
    ptype = frontmatter_meta.get("type")
    if ptype not in _VALID_TYPES:
        raise InvalidPageTypeError(
            f"invalid type '{ptype}'; must be one of {sorted(_VALID_TYPES)}."
        )
    title = str(frontmatter_meta.get("title") or "").strip()
    if not title:
        raise PageEditError("title is required.")

    meta = dict(frontmatter_meta)
    meta["title"] = title
    meta["updated_at"] = today()  # backend owns the timestamp, not the editor
    content = frontmatter.dump(meta, body)

    backend = ChangeRequestBackend(paths.root)
    result = backend.write(norm, content)
    if result.error is not None:
        raise PageEditError(result.error)
    changes = backend.collect_changes()
    if not changes:
        raise NoPageChangesError(f"no changes for '{norm}' — content identical to disk.")
    return change_request_service.create_from_changes(
        changes, f"Manual edit: {title}", paths, conn
    )
