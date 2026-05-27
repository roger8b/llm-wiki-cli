from __future__ import annotations

from pathlib import Path

from llmwiki.services import rules_service as rs


def test_render_block_has_markers_and_brain() -> None:
    block = rs.render_block("my-brain")
    assert rs.START_MARKER in block and rs.END_MARKER in block
    assert "my-brain" in block
    assert "wiki ask" in block and "wiki ingest" in block


def test_upsert_creates_then_updates_then_appends(tmp_path: Path) -> None:
    f = tmp_path / "AGENTS.md"
    block = rs.render_block("b1")

    # created
    assert rs.upsert_block(f, block) == "created"
    assert f.read_text().count(rs.START_MARKER) == 1

    # updated (re-run replaces, never duplicates)
    block2 = rs.render_block("b2")
    assert rs.upsert_block(f, block2) == "updated"
    text = f.read_text()
    assert text.count(rs.START_MARKER) == 1
    assert "b2" in text and "b1" not in text


def test_append_preserves_existing_content(tmp_path: Path) -> None:
    f = tmp_path / "CLAUDE.md"
    f.write_text("# My project\n\nExisting rules.\n", encoding="utf-8")
    assert rs.upsert_block(f, rs.render_block("b")) == "appended"
    text = f.read_text()
    assert "Existing rules." in text
    assert text.count(rs.START_MARKER) == 1


def test_remove_block(tmp_path: Path) -> None:
    f = tmp_path / "AGENTS.md"
    f.write_text("# Header\n\nkeep me\n", encoding="utf-8")
    rs.upsert_block(f, rs.render_block("b"))
    assert rs.remove_block(f) is True
    text = f.read_text()
    assert rs.START_MARKER not in text
    assert "keep me" in text  # surrounding content preserved
    # idempotent: removing again is a no-op
    assert rs.remove_block(f) is False
