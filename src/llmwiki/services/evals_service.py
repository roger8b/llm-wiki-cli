"""Agent evals harness (issue #175, Phase 0).

Reproducible quality measurement for the ingestion agent. Ingests a versioned
dataset of test sources into a throwaway brain, then scores each case against
its ``expected.json`` (page count, expected titles/types, wikilink resolution,
frontmatter validity, and — for the duplicate case — whether the agent created
a duplicate page instead of editing the existing one).

The runner is injectable (``ingest_service.Runner``) so CI can exercise the
harness mechanics with a fake agent and no network calls. Real runs use the
configured LLM.

This service NEVER touches the user's ``~/.wiki`` or active brain: it redirects
``WIKI_HOME`` to a temporary directory for the duration of the run, so the
throwaway brain's registry and database live in the temp dir only.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from ..core import frontmatter, markdown
from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest, FileChange, PageType
from ..core.paths import BrainPaths
from ..db.connection import get_connection
from . import change_request_service, ingest_service
from .ingest_service import Runner

logger = logging.getLogger("llmwiki.services.evals")

_SPECIAL = {"index.md", "log.md"}
_VALID_TYPES = {t.value for t in PageType}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EvalExpectation(BaseModel):
    """Expected outcome for one dataset source (its ``*.expected.json``)."""

    min_pages: int = 1
    max_pages: int = 999
    expected_titles_any: list[str] = Field(default_factory=list)
    # type -> minimum number of pages of that type the case should produce.
    expected_types: dict[str, int] = Field(default_factory=dict)
    # Pairs [a, b]: page titled ``a`` should wikilink to page titled ``b``.
    must_link: list[list[str]] = Field(default_factory=list)
    # True for the dedup case: ingesting should EDIT an existing page, not create
    # a brand-new duplicate. A ``create`` operation here is a failure.
    expect_edit: bool = False


class CaseResult(BaseModel):
    name: str
    score: float = 0.0
    pages_created: int = 0
    pages_updated: int = 0
    min_pages: int = 0
    max_pages: int = 0
    titles_found: list[str] = Field(default_factory=list)
    expected_titles_matched: bool = True
    types_ok: bool = True
    link_total: int = 0
    link_resolved: int = 0
    link_resolution_pct: float = 1.0
    frontmatter_valid_pct: float = 1.0
    must_link_ok: bool = True
    duplicate_created: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    used_fallback: bool = False
    notes: list[str] = Field(default_factory=list)


class EvalsReport(BaseModel):
    model: str
    timestamp: str
    cases: list[CaseResult] = Field(default_factory=list)
    score: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def _load_cases(dataset_dir: Path) -> list[tuple[Path, EvalExpectation]]:
    """Return ``(source_file, expectation)`` pairs sorted by filename.

    A case is a ``*.md`` file paired with ``<stem>.expected.json``.
    """
    cases: list[tuple[Path, EvalExpectation]] = []
    for src in sorted(dataset_dir.glob("*.md")):
        expected_file = src.with_suffix(".expected.json")
        if not expected_file.is_file():
            logger.warning("evals: no expectation for %s, skipping.", src.name)
            continue
        exp = EvalExpectation.model_validate_json(expected_file.read_text(encoding="utf-8"))
        cases.append((src, exp))
    return cases


# ---------------------------------------------------------------------------
# Wiki inspection helpers
# ---------------------------------------------------------------------------


def _wiki_title_map(paths: BrainPaths) -> dict[str, str]:
    """slug(title) and slug(stem) -> page path, across the whole wiki."""
    out: dict[str, str] = {}
    if not paths.wiki.is_dir():
        return out
    for file in paths.wiki.rglob("*.md"):
        if file.name in _SPECIAL:
            continue
        rel = paths.relative(file)
        text = file.read_text(encoding="utf-8")
        try:
            meta, body = frontmatter.parse(text)
        except Exception:  # noqa: BLE001
            meta, body = {}, text
        title = meta.get("title") or markdown.extract_title(body) or file.stem
        out[markdown.slugify(str(title))] = rel
        out[markdown.slugify(file.stem)] = rel
    return out


def _read_page(paths: BrainPaths, rel: str) -> tuple[dict[str, object], str] | None:
    file = paths.root / rel
    if not file.is_file():
        return None
    text = file.read_text(encoding="utf-8")
    try:
        meta, body = frontmatter.parse(text)
        return dict(meta), body
    except Exception:  # noqa: BLE001
        return {}, text


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Weights per metric (sum = 100).
_W_PAGES = 30
_W_TITLES = 20
_W_TYPES = 15
_W_MUST_LINK = 15
_W_LINKS = 10
_W_FRONTMATTER = 10


def _score_case(r: CaseResult) -> float:
    """Combine the case's metrics into a weighted 0–100 score."""
    total = r.pages_created + r.pages_updated
    score = 0.0
    if r.min_pages <= total <= r.max_pages:
        score += _W_PAGES
    if r.expected_titles_matched:
        score += _W_TITLES
    if r.types_ok:
        score += _W_TYPES
    if r.must_link_ok:
        score += _W_MUST_LINK
    score += _W_LINKS * r.link_resolution_pct
    score += _W_FRONTMATTER * r.frontmatter_valid_pct
    # The dedup case is a hard failure if a duplicate page was created.
    if r.duplicate_created:
        score = min(score, 25.0)
    return round(score, 1)


def _evaluate_case(
    name: str,
    exp: EvalExpectation,
    changes: list[FileChange],
    execution: dict[str, object] | None,
    paths: BrainPaths,
) -> CaseResult:
    created = [c for c in changes if c.operation == "create"]
    updated = [c for c in changes if c.operation == "update"]
    touched_paths = [c.path for c in created + updated]

    r = CaseResult(
        name=name,
        pages_created=len(created),
        pages_updated=len(updated),
        min_pages=exp.min_pages,
        max_pages=exp.max_pages,
    )
    if execution:

        def _int(key: str) -> int:
            val = execution.get(key, 0)
            return int(val) if isinstance(val, int | float) else 0

        r.tokens_in = _int("tokens_in")
        r.tokens_out = _int("tokens_out")
        r.latency_ms = _int("latency_ms")
        r.used_fallback = bool(execution.get("used_fallback", False))

    # Titles + types from the pages this case touched.
    titles: list[str] = []
    type_counts: dict[str, int] = {}
    valid_fm = 0
    for rel in touched_paths:
        page = _read_page(paths, rel)
        if page is None:
            continue
        meta, body = page
        title = meta.get("title") or markdown.extract_title(body) or Path(rel).stem
        titles.append(str(title))
        ptype = meta.get("type")
        if isinstance(ptype, str):
            type_counts[ptype] = type_counts.get(ptype, 0) + 1
        # Valid frontmatter = non-empty meta with a recognised type.
        if meta and isinstance(ptype, str) and ptype in _VALID_TYPES:
            valid_fm += 1
    r.titles_found = titles

    if exp.expected_titles_any:
        want = {markdown.slugify(t) for t in exp.expected_titles_any}
        have = {markdown.slugify(t) for t in titles}
        r.expected_titles_matched = bool(want & have)
        if not r.expected_titles_matched:
            r.notes.append("none of the expected titles were produced")

    for wanted_type, min_count in exp.expected_types.items():
        if type_counts.get(wanted_type, 0) < min_count:
            r.types_ok = False
            r.notes.append(
                f"expected >= {min_count} '{wanted_type}' page(s), "
                f"got {type_counts.get(wanted_type, 0)}"
            )

    if touched_paths:
        r.frontmatter_valid_pct = round(valid_fm / len(touched_paths), 3)

    # Wikilink resolution across this case's pages, against the whole wiki.
    title_map = _wiki_title_map(paths)
    link_total = 0
    link_resolved = 0
    for rel in touched_paths:
        page = _read_page(paths, rel)
        if page is None:
            continue
        _, body = page
        for target in markdown.extract_wikilinks(body):
            link_total += 1
            if markdown.slugify(target) in title_map:
                link_resolved += 1
    r.link_total = link_total
    r.link_resolved = link_resolved
    r.link_resolution_pct = round(link_resolved / link_total, 3) if link_total else 1.0

    # must_link pairs.
    for pair in exp.must_link:
        if len(pair) != 2:
            continue
        a, b = pair
        a_path = title_map.get(markdown.slugify(a))
        if a_path is None:
            r.must_link_ok = False
            r.notes.append(f"must_link source '{a}' not found")
            continue
        page = _read_page(paths, a_path)
        body = page[1] if page else ""
        resolves = any(
            markdown.slugify(t) == markdown.slugify(b)
            for t in markdown.extract_wikilinks(body)
        )
        if not resolves:
            r.must_link_ok = False
            r.notes.append(f"'{a}' does not link to '{b}'")

    # Dedup case: any create is a duplicate.
    if exp.expect_edit and created:
        r.duplicate_created = True
        r.notes.append(
            f"expected an edit but created {len(created)} new page(s): "
            f"{[c.path for c in created]}"
        )

    r.score = _score_case(r)
    return r


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_evals(
    cfg: WorkspaceConfig,
    *,
    dataset_dir: Path,
    keep_brain: bool = False,
    runner: Runner | None = None,
) -> EvalsReport:
    """Ingest the dataset into a throwaway brain and score each case.

    ``cfg`` supplies the LLM (model/provider); its ``brain_root`` is overridden
    to point at the temporary brain. Pass ``runner`` to use a fake agent (CI).
    The temp brain is deleted unless ``keep_brain`` is set.
    """
    from ..core import paths as _paths_mod
    from ..core.misc import now_iso

    cases = _load_cases(dataset_dir)
    if not cases:
        raise ValueError(f"No eval cases found in {dataset_dir}")

    workdir = Path(tempfile.mkdtemp(prefix="llmwiki-evals-"))
    saved_home = _paths_mod.WIKI_HOME
    _paths_mod.WIKI_HOME = workdir / "_home"
    _paths_mod.WIKI_HOME.mkdir(parents=True, exist_ok=True)

    results: list[CaseResult] = []
    try:
        from . import scaffold_service

        paths = scaffold_service.init_brain(workdir / "brain", git=False)
        eval_cfg = cfg.model_copy(update={"brain_root": paths.root})
        conn = get_connection(paths.db_path)
        try:
            for src, exp in cases:
                dest = paths.raw / "articles" / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                try:
                    cr = ingest_service.ingest(dest, paths, conn, eval_cfg, runner=runner)
                except Exception as exc:  # noqa: BLE001
                    logger.error("evals: ingest failed for %s: %s", src.name, exc)
                    results.append(
                        CaseResult(name=src.stem, notes=[f"ingest failed: {exc}"])
                    )
                    continue
                changes = list(cr.changes)
                if cr.files_changed:
                    change_request_service.apply(cr.id, paths, conn)
                results.append(
                    _evaluate_case(src.stem, exp, changes, _cr_execution(cr), paths)
                )
        finally:
            conn.close()
    finally:
        _paths_mod.WIKI_HOME = saved_home
        if not keep_brain:
            shutil.rmtree(workdir, ignore_errors=True)

    agg = round(sum(r.score for r in results) / len(results), 1) if results else 0.0
    return EvalsReport(
        model=cfg.model,
        timestamp=now_iso(),
        cases=results,
        score=agg,
        total_tokens_in=sum(r.tokens_in for r in results),
        total_tokens_out=sum(r.tokens_out for r in results),
    )


def _cr_execution(cr: ChangeRequest) -> dict[str, object] | None:
    """Read the execution telemetry persisted in the CR's meta.json."""
    meta_file = Path(cr.diff_dir) / "meta.json"
    if not meta_file.is_file():
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    execution = data.get("execution")
    return execution if isinstance(execution, dict) else None


def write_result_json(report: EvalsReport, cwd: Path) -> Path:
    """Persist the report under ``evals/results/<ts>-<model>.json`` in ``cwd``."""
    safe_model = report.model.replace(":", "-").replace("/", "-")
    ts = report.timestamp.replace(":", "").replace("-", "").replace(".", "")[:15]
    out_dir = cwd / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{ts}-{safe_model}.json"
    out_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return out_file
