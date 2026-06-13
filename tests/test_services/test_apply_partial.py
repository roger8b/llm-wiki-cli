"""Per-file partial apply/reject of a change request (#184)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llmwiki.core.models import FileChange
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import change_request_service as crs


def _make_cr(brain: BrainPaths, names: list[str]):
    changes = [
        FileChange(
            path=f"wiki/concepts/{n}.md",
            operation="create",
            new_content=f"---\ntitle: {n}\ntype: concept\n---\n# {n}\nBody.\n",
            diff=f"+{n}",
        )
        for n in names
    ]
    conn = get_connection(brain.db_path)
    try:
        return crs.create_from_changes(changes, "multi", brain, conn)
    finally:
        conn.close()


def _meta(cr) -> dict:
    return json.loads((Path(cr.diff_dir) / "meta.json").read_text(encoding="utf-8"))


class TestPartialApply:
    def test_applies_subset_rejects_rest(self, brain: BrainPaths) -> None:
        cr = _make_cr(brain, ["a", "b", "c", "d"])
        conn = get_connection(brain.db_path)
        try:
            out = crs.apply(
                cr.id, brain, conn,
                paths_filter=["wiki/concepts/a.md", "wiki/concepts/b.md"],
            )
        finally:
            conn.close()
        assert out.status == "applied"
        # selected written to disk
        assert (brain.root / "wiki/concepts/a.md").exists()
        assert (brain.root / "wiki/concepts/b.md").exists()
        # rest NOT written
        assert not (brain.root / "wiki/concepts/c.md").exists()
        assert not (brain.root / "wiki/concepts/d.md").exists()
        # settlement persisted
        assert set(out.applied_paths) == {"wiki/concepts/a.md", "wiki/concepts/b.md"}
        assert set(out.rejected_paths) == {"wiki/concepts/c.md", "wiki/concepts/d.md"}
        assert _meta(cr)["rejected_paths"] == out.rejected_paths
        # log records only the applied ones
        log = brain.log_path.read_text(encoding="utf-8")
        assert "concepts/a.md" in log and "concepts/c.md" not in log

    def test_full_apply_no_filter_unchanged(self, brain: BrainPaths) -> None:
        cr = _make_cr(brain, ["a", "b"])
        conn = get_connection(brain.db_path)
        try:
            out = crs.apply(cr.id, brain, conn)
        finally:
            conn.close()
        assert out.status == "applied"
        assert (brain.root / "wiki/concepts/a.md").exists()
        assert (brain.root / "wiki/concepts/b.md").exists()
        assert out.rejected_paths == []

    def test_unknown_path_raises(self, brain: BrainPaths) -> None:
        cr = _make_cr(brain, ["a"])
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(crs.CRPathNotFoundError):
                crs.apply(cr.id, brain, conn, paths_filter=["wiki/concepts/zzz.md"])
        finally:
            conn.close()
        assert not (brain.root / "wiki/concepts/a.md").exists()  # nothing applied

    def test_empty_filter_raises(self, brain: BrainPaths) -> None:
        cr = _make_cr(brain, ["a"])
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(crs.CREmptyError):
                crs.apply(cr.id, brain, conn, paths_filter=[])
        finally:
            conn.close()

    def test_get_exposes_settlement(self, brain: BrainPaths) -> None:
        cr = _make_cr(brain, ["a", "b"])
        conn = get_connection(brain.db_path)
        try:
            crs.apply(cr.id, brain, conn, paths_filter=["wiki/concepts/a.md"])
            reloaded = crs.get(cr.id, conn)
        finally:
            conn.close()
        assert reloaded is not None
        assert reloaded.applied_paths == ["wiki/concepts/a.md"]
        assert reloaded.rejected_paths == ["wiki/concepts/b.md"]
