"""Tests for edit-before-apply on change requests (issue #183)."""

from __future__ import annotations

import pytest

from llmwiki.core.diff import make_diff
from llmwiki.core.models import FileChange
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import change_request_service as crs


def _seed_cr(brain: BrainPaths, *, path: str, content: str, on_disk: str | None = None) -> str:
    """Create a pending CR with a single create/update change."""
    if on_disk is not None:
        target = brain.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(on_disk, encoding="utf-8")
    old = on_disk or ""
    change = FileChange(
        path=path,
        operation="update" if on_disk is not None else "create",
        new_content=content,
        diff=make_diff(old, content, path),
    )
    conn = get_connection(brain.db_path)
    try:
        cr = crs.create_from_changes([change], "seed", brain, conn)
    finally:
        conn.close()
    return cr.id


def _update(brain: BrainPaths, cr_id: str, path: str, new_content: str):
    conn = get_connection(brain.db_path)
    try:
        return crs.update_change(cr_id, path, new_content, conn, brain)
    finally:
        conn.close()


class TestUpdateChange:
    def test_edits_content_and_regenerates_diff(self, brain: BrainPaths) -> None:
        path = "wiki/concepts/rag.md"
        cr_id = _seed_cr(brain, path=path, content="---\ntitle: RAG\n---\n# RAG\nold body\n")
        edited = "---\ntitle: RAG\ntype: concept\n---\n# RAG\nnew body\n"
        cr = _update(brain, cr_id, path, edited)
        assert cr.status == "pending_review"
        assert cr.edited_by_reviewer is True
        change = cr.changes[0]
        assert change.new_content == edited
        assert "new body" in change.diff
        assert "old body" not in change.diff

    def test_apply_writes_edited_content(self, brain: BrainPaths) -> None:
        path = "wiki/concepts/rag.md"
        seed = "---\ntitle: RAG\ntype: concept\n---\n# RAG\na\n"
        cr_id = _seed_cr(brain, path=path, content=seed)
        edited = "---\ntitle: RAG\ntype: concept\n---\n# RAG\nEDITED\n"
        _update(brain, cr_id, path, edited)
        conn = get_connection(brain.db_path)
        try:
            crs.apply(cr_id, brain, conn)
        finally:
            conn.close()
        assert (brain.root / path).read_text(encoding="utf-8") == edited

    def test_status_not_pending_raises(self, brain: BrainPaths) -> None:
        path = "wiki/concepts/rag.md"
        seed = "---\ntitle: RAG\ntype: concept\n---\n# RAG\na\n"
        cr_id = _seed_cr(brain, path=path, content=seed)
        conn = get_connection(brain.db_path)
        try:
            crs.apply(cr_id, brain, conn)
        finally:
            conn.close()
        with pytest.raises(crs.CRStatusError):
            _update(brain, cr_id, path, "---\ntitle: RAG\n---\n# RAG\nb\n")

    def test_unknown_path_raises(self, brain: BrainPaths) -> None:
        cr_id = _seed_cr(brain, path="wiki/concepts/rag.md", content="# RAG\n")
        with pytest.raises(crs.CRPathNotFoundError):
            _update(brain, cr_id, "wiki/concepts/other.md", "x")

    def test_invalid_path_raises(self, brain: BrainPaths) -> None:
        cr_id = _seed_cr(brain, path="wiki/concepts/rag.md", content="# RAG\n")
        with pytest.raises(crs.CRInvalidPathError):
            _update(brain, cr_id, "raw/articles/x.md", "x")

    def test_unknown_cr_raises(self, brain: BrainPaths) -> None:
        with pytest.raises(crs.CRNotFoundError):
            _update(brain, "CR-2099-9999", "wiki/concepts/rag.md", "x")

    def test_edit_matching_disk_removes_change(self, brain: BrainPaths) -> None:
        # CR with two changes; editing one back to disk content drops it.
        disk = "---\ntitle: A\ntype: concept\n---\n# A\nsame\n"
        (brain.root / "wiki/concepts/a.md").parent.mkdir(parents=True, exist_ok=True)
        (brain.root / "wiki/concepts/a.md").write_text(disk, encoding="utf-8")
        c1 = FileChange(
            path="wiki/concepts/a.md", operation="update",
            new_content="---\ntitle: A\ntype: concept\n---\n# A\nchanged\n",
            diff=make_diff(disk, "changed", "wiki/concepts/a.md"),
        )
        c2 = FileChange(
            path="wiki/concepts/b.md", operation="create",
            new_content="# B\n", diff=make_diff("", "# B\n", "wiki/concepts/b.md"),
        )
        conn = get_connection(brain.db_path)
        try:
            cr = crs.create_from_changes([c1, c2], "seed", brain, conn)
        finally:
            conn.close()
        updated = _update(brain, cr.id, "wiki/concepts/a.md", disk)
        assert updated.files_changed == 1
        assert [c.path for c in updated.changes] == ["wiki/concepts/b.md"]

    def test_emptying_cr_raises(self, brain: BrainPaths) -> None:
        disk = "---\ntitle: A\ntype: concept\n---\n# A\nsame\n"
        cr_id = _seed_cr(
            brain, path="wiki/concepts/a.md",
            content="---\ntitle: A\ntype: concept\n---\n# A\nchanged\n", on_disk=disk,
        )
        with pytest.raises(crs.CREmptyError):
            _update(brain, cr_id, "wiki/concepts/a.md", disk)


class TestUpdateEndpoint:
    @pytest.fixture
    def client(self, brain: BrainPaths, monkeypatch):
        monkeypatch.setenv("WIKI_BRAIN", str(brain.root))
        from fastapi.testclient import TestClient

        from llmwiki.interfaces.api.main import app

        return TestClient(app)

    def test_patch_updates_file(self, client, brain: BrainPaths) -> None:
        path = "wiki/concepts/rag.md"
        seed = "---\ntitle: RAG\ntype: concept\n---\n# RAG\na\n"
        cr_id = _seed_cr(brain, path=path, content=seed)
        r = client.patch(
            f"/api/change-requests/{cr_id}/files",
            json={"path": path, "new_content": "---\ntitle: RAG\ntype: concept\n---\n# RAG\nB\n"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "pending_review"
        assert body["edited_by_reviewer"] is True

    def test_patch_unknown_path_404(self, client, brain: BrainPaths) -> None:
        cr_id = _seed_cr(brain, path="wiki/concepts/rag.md", content="# RAG\n")
        r = client.patch(
            f"/api/change-requests/{cr_id}/files",
            json={"path": "wiki/concepts/x.md", "new_content": "y"},
        )
        assert r.status_code == 404

    def test_patch_invalid_path_400(self, client, brain: BrainPaths) -> None:
        cr_id = _seed_cr(brain, path="wiki/concepts/rag.md", content="# RAG\n")
        r = client.patch(
            f"/api/change-requests/{cr_id}/files",
            json={"path": "raw/x.md", "new_content": "y"},
        )
        assert r.status_code == 400
