"""Change Request service: persiste, lista, aplica e rejeita propostas de mudança.

Um change request é o canal pelo qual o LLM altera a wiki: ele é criado a partir
das mudanças capturadas pelo ChangeRequestBackend, revisado pelo humano, e só então
aplicado (escrito no disco). Os diffs + conteúdo final ficam em
``.llmwiki/change_requests/CR-.../meta.json``.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime

from ..core.misc import now_iso, today
from ..core.models import ChangeRequest, FileChange
from ..core.paths import BrainPaths
from ..db.repo import ChangeRequestRepo, SourceRepo
from . import index_service


def create_from_changes(
    changes: list[FileChange],
    summary: str | None,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    job_id: int | None = None,
    source_path: str | None = None,
) -> ChangeRequest:
    """Cria um CR a partir das mudanças capturadas. Status inicial: pending_review."""
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
    )


def _load_changes(diff_dir: str) -> tuple[list[FileChange], str | None]:
    from pathlib import Path

    meta = json.loads((Path(diff_dir) / "meta.json").read_text(encoding="utf-8"))
    changes = [FileChange.model_validate(c) for c in meta.get("changes", [])]
    return changes, meta.get("source_path")


def get(cr_id: str, conn: sqlite3.Connection) -> ChangeRequest | None:
    row = ChangeRequestRepo(conn).get(cr_id)
    if row is None:
        return None
    changes, _ = _load_changes(row["diff_dir"])
    return ChangeRequest(
        id=row["id"],
        status=row["status"],
        summary=row["summary"],
        files_changed=row["files_changed"],
        diff_dir=row["diff_dir"],
        created_at=datetime.fromisoformat(row["created_at"]),
        applied_at=datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
        changes=changes,
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
) -> ChangeRequest:
    """Escreve as mudanças no disco, reindexa, registra no log e marca o CR aplicado."""
    repo = ChangeRequestRepo(conn)
    row = repo.get(cr_id)
    if row is None:
        raise ValueError(f"Change request não encontrado: {cr_id}")
    if row["status"] != "pending_review":
        raise ValueError(f"CR {cr_id} já está '{row['status']}'.")

    changes, source_path = _load_changes(row["diff_dir"])
    for change in changes:
        target = paths.root / change.path
        if change.operation == "delete":
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.new_content or "", encoding="utf-8")

    index_service.reindex(paths, conn)
    index_service.rebuild_index_md(paths, conn)
    _append_log(paths, cr_id, changes)

    if source_path:
        SourceRepo(conn).mark_processed(source_path)

    repo.set_status(cr_id, "applied", applied=True)

    if git_commit:
        _git_commit(paths, cr_id)

    cr = get(cr_id, conn)
    assert cr is not None
    return cr


def reject(cr_id: str, conn: sqlite3.Connection) -> None:
    repo = ChangeRequestRepo(conn)
    row = repo.get(cr_id)
    if row is None:
        raise ValueError(f"Change request não encontrado: {cr_id}")
    repo.set_status(cr_id, "rejected")


def _append_log(paths: BrainPaths, cr_id: str, changes: list[FileChange]) -> None:
    paths.log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"- {today()}: aplicado {cr_id} ({len(changes)} arquivos)"]
    for c in changes:
        lines.append(f"    - {c.operation}: {c.path}")
    existing = (
        paths.log_path.read_text(encoding="utf-8")
        if paths.log_path.exists()
        else "# Log da Wiki\n"
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
