"""Manual page edit proposed as a change request (#186)."""

from __future__ import annotations

import pytest

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import change_request_service, page_service


def _seed(brain: BrainPaths) -> str:
    p = brain.wiki / "concepts" / "rag.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: RAG\ntype: concept\ntags: [ai]\nconfidence: medium\n---\n# RAG\nOld body.\n",
        encoding="utf-8",
    )
    return "wiki/concepts/rag.md"


class TestProposeEdit:
    def test_creates_pending_cr_without_writing(self, brain: BrainPaths) -> None:
        path = _seed(brain)
        before = (brain.root / path).read_text(encoding="utf-8")
        conn = get_connection(brain.db_path)
        try:
            cr = page_service.propose_edit(
                path,
                {"title": "RAG", "type": "concept", "tags": ["ai"], "confidence": "high"},
                "# RAG\nNew body with more detail.\n",
                brain,
                conn,
            )
        finally:
            conn.close()
        assert cr.status == "pending_review"
        assert cr.files_changed == 1
        assert cr.summary == "Manual edit: RAG"
        # page on disk is unchanged until the CR is applied
        assert (brain.root / path).read_text(encoding="utf-8") == before

    def test_apply_writes_edit(self, brain: BrainPaths) -> None:
        path = _seed(brain)
        conn = get_connection(brain.db_path)
        try:
            cr = page_service.propose_edit(
                path,
                {"title": "RAG", "type": "concept"},
                "# RAG\nApplied body.\n",
                brain,
                conn,
            )
            change_request_service.apply(cr.id, brain, conn)
        finally:
            conn.close()
        text = (brain.root / path).read_text(encoding="utf-8")
        assert "Applied body." in text
        assert "updated_at:" in text  # backend stamped it

    def test_invalid_type_rejected(self, brain: BrainPaths) -> None:
        path = _seed(brain)
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(page_service.InvalidPageTypeError):
                page_service.propose_edit(
                    path, {"title": "RAG", "type": "bogus"}, "# RAG\nx\n", brain, conn
                )
        finally:
            conn.close()

    def test_empty_title_rejected(self, brain: BrainPaths) -> None:
        path = _seed(brain)
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(page_service.PageEditError):
                page_service.propose_edit(
                    path, {"title": "  ", "type": "concept"}, "# x\n", brain, conn
                )
        finally:
            conn.close()

    def test_no_change_raises(self, brain: BrainPaths) -> None:
        path = _seed(brain)
        conn = get_connection(brain.db_path)
        try:
            # First edit, then re-propose the identical content.
            cr = page_service.propose_edit(
                path, {"title": "RAG", "type": "concept"}, "# RAG\nB.\n", brain, conn
            )
            change_request_service.apply(cr.id, brain, conn)
            current = (brain.root / path).read_text(encoding="utf-8")
            from llmwiki.core import frontmatter

            meta, body = frontmatter.parse(current)
            with pytest.raises(page_service.NoPageChangesError):
                page_service.propose_edit(path, meta, body, brain, conn)
        finally:
            conn.close()
