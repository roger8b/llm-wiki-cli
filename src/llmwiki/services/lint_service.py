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
from dataclasses import dataclass, field
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


def titles_from_contents(files: dict[str, str]) -> dict[str, str]:
    """Build slug(title)->path and slug(stem)->path from in-memory contents.

    Used to resolve wikilinks both on disk and against a change-request staging
    area, so a link to a sibling page created in the same run still resolves.
    """
    title_to_path: dict[str, str] = {}
    for rel, text in files.items():
        try:
            meta, body = frontmatter.parse(text)
        except InvalidFrontmatterError:
            meta, body = {}, text
        stem = Path(rel).stem
        title = (meta.get("title") if meta else None) or markdown.extract_title(body) or stem
        title_to_path[markdown.slugify(str(title))] = rel
        title_to_path[markdown.slugify(stem)] = rel
    return title_to_path


def lint_contents(
    files: dict[str, str], *, known_titles: dict[str, str]
) -> list[LintFinding]:
    """Validate page contents in memory (frontmatter, type, wikilinks).

    Shared by ``lint_structural`` (disk) and the ingestion self-correction loop
    (#166), which lints the backend's staging before creating a change request.
    Orphan detection is intentionally NOT here: a brand-new staged page may be
    linked only after the run, so it is not an orphan yet. ``known_titles`` maps
    ``slug -> path`` for link resolution (disk + staging for the staging case).
    """
    findings: list[LintFinding] = []
    for rel in sorted(files):
        text = files[rel]
        try:
            meta, _ = frontmatter.parse(text)
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

        for target in markdown.extract_wikilinks(text):
            if _resolve_wikilink(target, known_titles) is None:
                findings.append(
                    LintFinding(
                        kind="broken_link",
                        severity=Severity.error,
                        message=f"{rel}: link [[{target}]] does not resolve to any page.",
                        pages=[rel],
                    )
                )
    return findings


def lint_structural(
    paths: BrainPaths, conn: sqlite3.Connection | None = None
) -> list[LintFinding]:
    files = {paths.relative(f): f.read_text(encoding="utf-8") for f in _iter_wiki_files(paths.wiki)}
    known_titles = titles_from_contents(files)

    findings = lint_contents(files, known_titles=known_titles)

    # Orphans (disk-only): a page with no incoming resolved links. Only pages
    # with parseable frontmatter act as link sources (mirrors the legacy pass).
    incoming: dict[str, int] = {rel: 0 for rel in files}
    for rel, text in files.items():
        try:
            frontmatter.parse(text)
        except InvalidFrontmatterError:
            continue
        for target in markdown.extract_wikilinks(text):
            dest = _resolve_wikilink(target, known_titles)
            if dest is not None and dest != rel:
                incoming[dest] = incoming.get(dest, 0) + 1
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


# ----------------------------------------------------------------------------
# Batched semantic lint with a token budget (#173)
# ----------------------------------------------------------------------------

_SEVERITY_RANK = {Severity.info: 1, Severity.warn: 2, Severity.error: 3}


@dataclass
class Batch:
    """A named group of page paths audited together in one runner invocation."""

    name: str
    pages: list[str]


@dataclass
class LintBatchReport:
    """Result of a batched semantic lint run."""

    findings: list[LintFinding] = field(default_factory=list)
    processed: list[Batch] = field(default_factory=list)
    skipped: list[Batch] = field(default_factory=list)

    @property
    def pages_covered(self) -> list[str]:
        seen: list[str] = []
        for b in self.processed:
            seen.extend(b.pages)
        return seen


BatchRunner = Callable[[WorkspaceConfig, Batch], list[LintFinding]]


def _estimate_tokens(paths: BrainPaths, rels: list[str]) -> int:
    """Rough token estimate (chars / 4) for the given relative page paths."""
    total = 0
    for rel in rels:
        p = paths.root / rel
        try:
            total += len(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return total // 4


def partition_pages(
    paths: BrainPaths, *, budget: int, scope: str | None = None
) -> tuple[list[Batch], list[Batch]]:
    """Group wiki pages into batches by type directory under a token ``budget``.

    Returns ``(to_process, skipped)``. Pages are grouped by their type directory
    (``concepts/``, ``entities/``, …); a directory larger than ``budget`` is
    split alphabetically into sub-batches. Batches that don't fit the total run
    budget are returned as ``skipped`` (never silently dropped). The first batch
    always runs so a single oversized batch is not skipped to nothing.
    """
    groups: dict[str, list[str]] = {}
    for f in _iter_wiki_files(paths.wiki):
        rel = paths.relative(f)
        parts = Path(rel).parts  # ("wiki", "concepts", "a.md")
        type_dir = parts[1] if len(parts) > 2 else "_root"
        if scope is not None and type_dir != scope:
            continue
        groups.setdefault(type_dir, []).append(rel)

    candidates: list[Batch] = []
    for type_dir in sorted(groups):
        rels = sorted(groups[type_dir])
        if _estimate_tokens(paths, rels) <= budget:
            candidates.append(Batch(name=type_dir, pages=rels))
            continue
        # Directory exceeds budget → split alphabetically into sub-batches.
        cur: list[str] = []
        cur_tok = 0
        idx = 1
        for rel in rels:
            tok = _estimate_tokens(paths, [rel])
            if cur and cur_tok + tok > budget:
                candidates.append(Batch(name=f"{type_dir} ({idx})", pages=cur))
                idx += 1
                cur, cur_tok = [], 0
            cur.append(rel)
            cur_tok += tok
        if cur:
            candidates.append(Batch(name=f"{type_dir} ({idx})", pages=cur))

    to_process: list[Batch] = []
    skipped: list[Batch] = []
    used = 0
    for b in candidates:
        tok = _estimate_tokens(paths, b.pages)
        if to_process and used + tok > budget:
            skipped.append(b)
        else:
            to_process.append(b)
            used += tok
    return to_process, skipped


def _consolidate(findings: list[LintFinding]) -> list[LintFinding]:
    """Dedup findings sharing ``(kind, sorted(pages))``; keep highest severity."""
    by_key: dict[tuple[str, tuple[str, ...]], LintFinding] = {}
    for f in findings:
        key = (f.kind, tuple(sorted(f.pages)))
        cur = by_key.get(key)
        if cur is None or _SEVERITY_RANK[f.severity] > _SEVERITY_RANK[cur.severity]:
            by_key[key] = f
    return list(by_key.values())


def _default_batch_runner(cfg: WorkspaceConfig, batch: Batch) -> list[LintFinding]:
    from ..llm_agents.factory import run_lint

    report = run_lint(cfg, pages=batch.pages, scope_name=batch.name)
    out: list[LintFinding] = []
    for f in report.findings:
        try:
            sev = Severity(f.severity)
        except ValueError:
            sev = Severity.warn
        out.append(LintFinding(kind=f.kind, severity=sev, message=f.message, pages=f.pages))
    return out


def lint_batched(
    paths: BrainPaths,
    cfg: WorkspaceConfig,
    *,
    scope: str | None = None,
    structural: bool = True,
    batch_runner: BatchRunner | None = None,
) -> LintBatchReport:
    """Run structural lint plus batched semantic lint within the token budget."""
    findings: list[LintFinding] = []
    if structural:
        findings.extend(lint_structural(paths))
        if scope is not None:
            prefix = f"wiki/{scope}/"
            findings = [
                f for f in findings if any(p.startswith(prefix) for p in f.pages)
            ]

    to_process, skipped = partition_pages(
        paths, budget=cfg.lint_token_budget, scope=scope
    )
    runner = batch_runner or _default_batch_runner
    for batch in to_process:
        findings.extend(runner(cfg, batch))

    return LintBatchReport(
        findings=_consolidate(findings),
        processed=to_process,
        skipped=skipped,
    )


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
