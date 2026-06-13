"""Change Request service: persists, lists, applies, and rejects change requests.

A change request is the channel through which the LLM updates the wiki: it is created from
changes captured by the ChangeRequestBackend, reviewed by a human, and only then
applied (written to disk). Diffs and the final content are saved in
``.llmwiki/change_requests/CR-.../meta.json``.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from ..core.diff import make_diff
from ..core.misc import now_iso, today
from ..core.models import ChangeRequest, FileChange
from ..core.paths import BrainPaths
from ..db.repo import ChangeRequestRepo, SourceRepo
from . import index_service


class CRNotFoundError(ValueError):
    """The change request does not exist (HTTP 404)."""


class CRPathNotFoundError(ValueError):
    """The requested path is not part of the change request (HTTP 404)."""


class CRStatusError(ValueError):
    """The change request is not editable in its current status (HTTP 409)."""


class CRInvalidPathError(ValueError):
    """The path is outside the writable wiki/ allow-list (HTTP 400)."""


class CREmptyError(ValueError):
    """The edit would leave the CR with no changes — reject it instead (HTTP 409)."""


def create_from_changes(
    changes: list[FileChange],
    summary: str | None,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    job_id: int | None = None,
    source_path: str | None = None,
    execution: dict[str, object] | None = None,
    warnings: list[str] | None = None,
) -> ChangeRequest:
    """Creates a CR from captured changes. Initial status: pending_review.

    ``execution`` carries optional agent telemetry (model, tokens, latency,
    tool calls, fallback) persisted into ``meta.json`` for later auditing.
    ``warnings`` carries structural lint findings the agent could not auto-fix
    before the CR (#166), shown to the reviewer.
    """
    repo = ChangeRequestRepo(conn)
    cr_id = repo.next_id()
    diff_dir = paths.change_requests / cr_id
    diff_dir.mkdir(parents=True, exist_ok=True)

    for i, change in enumerate(changes):
        safe = change.path.replace("/", "__")
        (diff_dir / f"{i:03d}-{safe}.diff").write_text(change.diff, encoding="utf-8")

    created = now_iso()
    meta = {
        "id": cr_id,
        "summary": summary,
        "source_path": source_path,
        "created_at": created,
        "execution": execution,
        "warnings": warnings or [],
        "changes": [c.model_dump() for c in changes],
    }
    (diff_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    repo.insert(cr_id, summary, len(changes), str(diff_dir), job_id=job_id)
    return ChangeRequest(
        id=cr_id,
        summary=summary,
        files_changed=len(changes),
        diff_dir=str(diff_dir),
        created_at=datetime.fromisoformat(created),
        changes=changes,
        warnings=warnings or [],
    )


def _load_changes(diff_dir: str) -> tuple[list[FileChange], str | None]:
    meta = json.loads((Path(diff_dir) / "meta.json").read_text(encoding="utf-8"))
    changes = [FileChange.model_validate(c) for c in meta.get("changes", [])]
    return changes, meta.get("source_path")


def _edited_by_reviewer(diff_dir: str) -> bool:
    meta_file = Path(diff_dir) / "meta.json"
    if not meta_file.is_file():
        return False
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(meta.get("edited_by_reviewer", False))


def _warnings(diff_dir: str) -> list[str]:
    meta_file = Path(diff_dir) / "meta.json"
    if not meta_file.is_file():
        return []
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    value = meta.get("warnings")
    return [str(w) for w in value] if isinstance(value, list) else []


def _settled_paths(diff_dir: str) -> tuple[list[str], list[str]]:
    """Read ``applied_paths`` / ``rejected_paths`` from the CR meta (#184)."""
    meta_file = Path(diff_dir) / "meta.json"
    if not meta_file.is_file():
        return [], []
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    applied = meta.get("applied_paths")
    rejected = meta.get("rejected_paths")
    return (
        [str(p) for p in applied] if isinstance(applied, list) else [],
        [str(p) for p in rejected] if isinstance(rejected, list) else [],
    )


def get(cr_id: str, conn: sqlite3.Connection) -> ChangeRequest | None:
    row = ChangeRequestRepo(conn).get(cr_id)
    if row is None:
        return None
    changes, _ = _load_changes(row["diff_dir"])
    applied_paths, rejected_paths = _settled_paths(row["diff_dir"])
    return ChangeRequest(
        id=row["id"],
        status=row["status"],
        summary=row["summary"],
        files_changed=row["files_changed"],
        diff_dir=row["diff_dir"],
        created_at=datetime.fromisoformat(row["created_at"]),
        applied_at=datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
        changes=changes,
        edited_by_reviewer=_edited_by_reviewer(row["diff_dir"]),
        warnings=_warnings(row["diff_dir"]),
        applied_paths=applied_paths,
        rejected_paths=rejected_paths,
    )


def list_crs(conn: sqlite3.Connection, status: str | None = None) -> list[ChangeRequest]:
    out: list[ChangeRequest] = []
    for row in ChangeRequestRepo(conn).list(status):
        out.append(
            ChangeRequest(
                id=row["id"],
                status=row["status"],
                summary=row["summary"],
                files_changed=row["files_changed"],
                diff_dir=row["diff_dir"],
                created_at=datetime.fromisoformat(row["created_at"]),
                applied_at=datetime.fromisoformat(row["applied_at"])
                if row["applied_at"]
                else None,
            )
        )
    return out


def apply(
    cr_id: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    git_commit: bool = False,
    paths_filter: list[str] | None = None,
) -> ChangeRequest:
    """Writes changes to disk, reindexes, records to log, and marks the CR applied.

    Partial-apply semantics (#184): ``paths_filter`` selects which file paths to
    apply. The CR settles in a SINGLE decision — the selected paths are written
    and the remaining paths are recorded as rejected (``applied_paths`` /
    ``rejected_paths`` in ``meta.json``); the CR ends ``applied`` either way. Pass
    ``None`` (or the full set) for the original "apply everything" behaviour. An
    empty list is refused (reject the CR instead). A path not in the CR raises.
    """
    repo = ChangeRequestRepo(conn)
    row = repo.get(cr_id)
    if row is None:
        raise CRNotFoundError(f"Change request not found: {cr_id}")
    if row["status"] != "pending_review":
        raise CRStatusError(f"CR {cr_id} is already '{row['status']}'.")

    changes, source_path = _load_changes(row["diff_dir"])
    all_paths = [c.path for c in changes]

    if paths_filter is None:
        selected = list(all_paths)
    else:
        norm = [p.lstrip("/") for p in paths_filter]
        if not norm:
            raise CREmptyError(f"no paths selected for {cr_id}; reject it instead.")
        unknown = [p for p in norm if p not in all_paths]
        if unknown:
            raise CRPathNotFoundError(f"paths not in {cr_id}: {', '.join(unknown)}")
        selected = norm

    applied = [c for c in changes if c.path in set(selected)]
    rejected_paths = [p for p in all_paths if p not in set(selected)]

    # Defence in depth: re-validate every APPLIED path against the write
    # allow-list before touching the disk, so a malformed/malicious CR cannot
    # escape the wiki/ sandbox. Atomic: validate all before writing any.
    from ..llm_agents.backend import validate_change_path

    for change in applied:
        err = validate_change_path(change.path)
        if err is not None:
            raise CRInvalidPathError(f"CR {cr_id}: refusing to apply '{change.path}': {err}")

    for change in applied:
        target = paths.root / change.path
        if change.operation == "delete":
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.new_content or "", encoding="utf-8")

    index_service.reindex(paths, conn)
    index_service.rebuild_index_md(paths, conn)
    _append_log(paths, cr_id, applied)

    if source_path:
        SourceRepo(conn).mark_processed(source_path)

    _record_settlement(row["diff_dir"], [c.path for c in applied], rejected_paths)
    repo.set_status(cr_id, "applied", applied=True)

    if git_commit:
        _git_commit(paths, cr_id)

    cr = get(cr_id, conn)
    assert cr is not None
    return cr


def _record_settlement(
    diff_dir: str, applied_paths: list[str], rejected_paths: list[str]
) -> None:
    """Persist the per-file apply/reject decision into the CR meta (#184)."""
    meta_file = Path(diff_dir) / "meta.json"
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    meta["applied_paths"] = applied_paths
    meta["rejected_paths"] = rejected_paths
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _confidence_of(content: str) -> str | None:
    """Best-effort ``confidence`` frontmatter field (mirrors the backend)."""
    from ..core import frontmatter

    try:
        meta, _ = frontmatter.parse(content)
    except Exception:  # noqa: BLE001
        return None
    value = meta.get("confidence") if meta else None
    return str(value) if value is not None else None


def _rewrite_diff_files(diff_dir: Path, changes: list[FileChange]) -> None:
    """Replace the per-file ``.diff`` artifacts to match ``changes`` exactly."""
    for stale in diff_dir.glob("*.diff"):
        stale.unlink()
    for i, change in enumerate(changes):
        safe = change.path.replace("/", "__")
        (diff_dir / f"{i:03d}-{safe}.diff").write_text(change.diff, encoding="utf-8")


def update_change(
    cr_id: str,
    path: str,
    new_content: str,
    conn: sqlite3.Connection,
    paths: BrainPaths,
) -> ChangeRequest:
    """Edit one file's proposed content before the CR is applied (issue #183).

    Re-validates the path, regenerates the diff against the current disk
    content, recomputes ``confidence``, and marks the CR ``edited_by_reviewer``.
    An edit that matches the disk content removes the change (no-op); a CR left
    with zero changes is refused (reject it instead). The CR stays
    ``pending_review`` so a later apply writes the EDITED content.
    """
    from ..llm_agents.backend import validate_change_path

    repo = ChangeRequestRepo(conn)
    row = repo.get(cr_id)
    if row is None:
        raise CRNotFoundError(f"Change request not found: {cr_id}")
    if row["status"] != "pending_review":
        raise CRStatusError(f"CR {cr_id} is '{row['status']}', not editable.")

    norm = path.lstrip("/")
    err = validate_change_path(norm)
    if err is not None:
        raise CRInvalidPathError(f"refusing to edit '{path}': {err}")

    diff_dir = Path(row["diff_dir"])
    meta = json.loads((diff_dir / "meta.json").read_text(encoding="utf-8"))
    changes = [FileChange.model_validate(c) for c in meta.get("changes", [])]

    idx = next((i for i, c in enumerate(changes) if c.path == norm), None)
    if idx is None:
        raise CRPathNotFoundError(f"path '{path}' is not part of {cr_id}.")

    disk = paths.root / norm
    old = disk.read_text(encoding="utf-8") if disk.is_file() else ""

    if new_content == old:
        # The edit reverts the page to its on-disk state — drop the change.
        changes.pop(idx)
        if not changes:
            raise CREmptyError(
                f"editing '{path}' would empty {cr_id}; reject it instead."
            )
    else:
        operation = "update" if disk.is_file() else "create"
        changes[idx] = FileChange(
            path=norm,
            operation=operation,
            new_content=new_content,
            diff=make_diff(old, new_content, norm),
            category=changes[idx].category,
            confidence=_confidence_of(new_content),
        )

    _rewrite_diff_files(diff_dir, changes)
    meta["changes"] = [c.model_dump() for c in changes]
    meta["edited_by_reviewer"] = True
    meta["edited_at"] = now_iso()
    (diff_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    repo.set_files_changed(cr_id, len(changes))

    cr = get(cr_id, conn)
    assert cr is not None
    return cr


def reject(cr_id: str, conn: sqlite3.Connection) -> None:
    repo = ChangeRequestRepo(conn)
    row = repo.get(cr_id)
    if row is None:
        raise ValueError(f"Change request not found: {cr_id}")
    repo.set_status(cr_id, "rejected")


def _append_log(paths: BrainPaths, cr_id: str, changes: list[FileChange]) -> None:
    paths.log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"- {today()}: applied {cr_id} ({len(changes)} files)"]
    for c in changes:
        lines.append(f"    - {c.operation}: {c.path}")
    existing = (
        paths.log_path.read_text(encoding="utf-8")
        if paths.log_path.exists()
        else "# Wiki Log\n"
    )
    body = existing.rstrip("\n") + "\n" + "\n".join(lines) + "\n"
    paths.log_path.write_text(body, encoding="utf-8")


def _git_commit(paths: BrainPaths, cr_id: str) -> None:
    try:
        subprocess.run(["git", "add", "-A"], cwd=paths.root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", f"feat(wiki): apply {cr_id}"],
            cwd=paths.root,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
        pass
