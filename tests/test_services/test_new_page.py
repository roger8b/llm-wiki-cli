"""New-page templates + slug-collision guard (#187)."""

from __future__ import annotations

import pytest

from llmwiki.core.errors import PageExistsError
from llmwiki.core.models import PageType
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import page_service


def test_list_templates_one_body_per_type() -> None:
    templates = page_service.list_templates()
    by_type = {t["type"]: t["body"] for t in templates}
    assert set(by_type) == {t.value for t in PageType}
    # body is frontmatter-stripped and keeps the title placeholder
    assert "{{title}}" in by_type["decision"]
    assert "type:" not in by_type["decision"].splitlines()[0]


class TestCollision:
    def test_create_new_path_ok(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            cr = page_service.propose_edit(
                "wiki/decisions/use-sqlite-vec.md",
                {"title": "Use sqlite-vec", "type": "decision"},
                "# Use sqlite-vec\nBody.\n",
                brain,
                conn,
                expect_new=True,
            )
        finally:
            conn.close()
        assert cr.files_changed == 1
        assert cr.changes[0].operation == "create"

    def test_expect_new_collision_raises(self, brain: BrainPaths) -> None:
        page = brain.wiki / "decisions" / "x.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\ntitle: X\ntype: decision\n---\n# X\n", encoding="utf-8")
        conn = get_connection(brain.db_path)
        try:
            with pytest.raises(PageExistsError):
                page_service.propose_edit(
                    "wiki/decisions/x.md",
                    {"title": "X", "type": "decision"},
                    "# X\nnew\n",
                    brain,
                    conn,
                    expect_new=True,
                )
        finally:
            conn.close()
