"""Structural lint (deterministic, without LLM).

Checks:
- missing or invalid frontmatter
- invalid page type
- broken link ([[X]] with no corresponding page)
- orphan page (no incoming links)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from ..core import frontmatter, markdown
from ..core.config import WorkspaceConfig
from ..core.errors import InvalidFrontmatterError
from ..core.models import LintFinding, PageType, Severity
from ..core.paths import BrainPaths

_SPECIAL = {"index.md", "log.md"}
_VALID_TYPES = {t.value for t in PageType}


def _iter_wiki_files(wiki_dir: Path) -> list[Path]:
    if not wiki_dir.is_dir():
        return []
    return sorted(p for p in wiki_dir.rglob("*.md") if p.name not in _SPECIAL)


def _resolve_wikilink(target: str, known_titles: dict[str, str]) -> str | None:
    """Resolves a [[link]] target to a page path, by title (slug)."""
    return known_titles.get(markdown.slugify(target))


def lint_structural(
    paths: BrainPaths, conn: sqlite3.Connection | None = None
) -> list[LintFinding]:
    files = _iter_wiki_files(paths.wiki)
    findings: list[LintFinding] = []

    # Maps slug(title)->path and slug(filename)->path to resolve links.
    title_to_path: dict[str, str] = {}
    bodies: dict[str, str] = {}
    incoming: dict[str, int] = {}

    for file in files:
        rel = paths.relative(file)
        incoming.setdefault(rel, 0)
        text = file.read_text(encoding="utf-8")
        try:
            meta, body = frontmatter.parse(text)
        except InvalidFrontmatterError as exc:
            findings.append(
                LintFinding(
                    kind="invalid_frontmatter",
                    severity=Severity.error,
                    message=f"{rel}: {exc}",
                    pages=[rel],
                )
            )
            continue

        if not meta:
            findings.append(
                LintFinding(
                    kind="missing_frontmatter",
                    severity=Severity.warn,
                    message=f"{rel}: missing YAML frontmatter.",
                    pages=[rel],
                )
            )

        ptype = meta.get("type")
        if ptype is not None and ptype not in _VALID_TYPES:
            findings.append(
                LintFinding(
                    kind="invalid_page_type",
                    severity=Severity.warn,
                    message=f"{rel}: type '{ptype}' is invalid.",
                    pages=[rel],
                )
            )

        title = meta.get("title") or markdown.extract_title(body) or file.stem
        title_to_path[markdown.slugify(str(title))] = rel
        title_to_path[markdown.slugify(file.stem)] = rel
        bodies[rel] = text

    # Links: broken links + incoming count.
    for rel, text in bodies.items():
        for target in markdown.extract_wikilinks(text):
            dest = _resolve_wikilink(target, title_to_path)
            if dest is None:
                findings.append(
                    LintFinding(
                        kind="broken_link",
                        severity=Severity.error,
                        message=f"{rel}: link [[{target}]] does not resolve to any page.",
                        pages=[rel],
                    )
                )
            elif dest != rel:
                incoming[dest] = incoming.get(dest, 0) + 1

    # Orphans: no incoming links.
    for rel, count in sorted(incoming.items()):
        if count == 0:
            findings.append(
                LintFinding(
                    kind="orphan_page",
                    severity=Severity.warn,
                    message=f"{rel}: orphan page (no incoming links).",
                    pages=[rel],
                )
            )

    return findings


# runner(cfg) -> list[LintFinding] (semantic layer via LLM)
SemanticRunner = Callable[[WorkspaceConfig], list[LintFinding]]


def _default_semantic_runner(cfg: WorkspaceConfig) -> list[LintFinding]:
    from ..llm_agents.factory import run_lint

    report = run_lint(cfg)
    out: list[LintFinding] = []
    for f in report.findings:
        try:
            sev = Severity(f.severity)
        except ValueError:
            sev = Severity.warn
        out.append(LintFinding(kind=f.kind, severity=sev, message=f.message, pages=f.pages))
    return out


def lint_all(
    paths: BrainPaths,
    cfg: WorkspaceConfig,
    *,
    semantic: bool = True,
    semantic_runner: SemanticRunner | None = None,
) -> list[LintFinding]:
    """Combines structural lint (deterministic) and semantic lint (LLM)."""
    findings = lint_structural(paths)
    if semantic:
        runner = semantic_runner or _default_semantic_runner
        findings = findings + runner(cfg)
    return findings


def annotate_with_pending_crs(
    findings: list[LintFinding], conn: sqlite3.Connection
) -> list[LintFinding]:
    """Attach ``related_cr`` to findings whose page already has a pending fix.

    Lets a report say "broken_link … (CR-0042 already open fixes this)" so the
    user doesn't open a duplicate correction. Mutates and returns ``findings``.
    """
    from . import change_request_service

    page_to_cr: dict[str, str] = {}
    for cr in change_request_service.list_crs(conn, status="pending_review"):
        full = change_request_service.get(cr.id, conn)
        if full is None:
            continue
        for change in full.changes:
            page_to_cr.setdefault(change.path, cr.id)

    for finding in findings:
        for page in finding.pages:
            if page in page_to_cr:
                finding.related_cr = page_to_cr[page]
                break
    return findings
