"""Brain registry: registration, path lookup, and legacy-data migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import llmwiki.core.paths as _paths_mod
from llmwiki.core import brains
from llmwiki.core.brains import (
    BrainAlreadyRegisteredError,
    get_brain_by_path,
    is_brain_dir,
    migrate_legacy_data,
    register_or_get,
    update_brain,
)
from llmwiki.services import scaffold_service


def _seed_legacy_source(db: Path, rel_path: str) -> None:
    """Create a legacy metadata.db with one source row."""
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    # minimal schema slice used by the migration emptiness check + listing
    conn.executescript(
        """
        CREATE TABLE sources (id INTEGER PRIMARY KEY, path TEXT, type TEXT,
            title TEXT, hash TEXT, added_at TEXT, processed_at TEXT, status TEXT);
        CREATE TABLE wiki_pages (id INTEGER PRIMARY KEY);
        """
    )
    conn.execute(
        "INSERT INTO sources (path, type, hash, added_at, status) "
        "VALUES (?,?,?,?,?)",
        (rel_path, "md", "deadbeef", "2026-01-01T00:00:00Z", "pending"),
    )
    conn.commit()
    conn.close()


class TestRegistry:
    def test_is_brain_dir(self, brain) -> None:
        assert is_brain_dir(brain.root) is True
        assert is_brain_dir(brain.root / "nope") is False

    def test_get_brain_by_path(self, brain) -> None:
        found = get_brain_by_path(brain.root)
        assert found is not None and found.path == str(brain.root.resolve())

    def test_register_or_get_is_idempotent(self, brain) -> None:
        a = register_or_get(brain.root, activate=False)
        b = register_or_get(brain.root, activate=False)
        assert a.id == b.id  # same brain, not duplicated

    def test_update_brain_rejects_path_clash(self, tmp_path) -> None:
        b1 = scaffold_service.init_brain(tmp_path / "b1", git=False)
        b2 = scaffold_service.init_brain(tmp_path / "b2", git=False)
        id1 = get_brain_by_path(b1.root).id
        with pytest.raises(BrainAlreadyRegisteredError):
            update_brain(id1, {"path": str(b2.root)})


class TestUnifiedResolver:
    def test_resolve_active_uses_registry_not_cwd(self, tmp_path, monkeypatch) -> None:
        # Two brains; resolve_active must follow the registry active, regardless
        # of the current working directory.
        a = scaffold_service.init_brain(tmp_path / "A", git=False)
        b = scaffold_service.init_brain(tmp_path / "B", git=False)
        monkeypatch.delenv("WIKI_BRAIN", raising=False)
        monkeypatch.chdir(tmp_path)  # neutral cwd (not inside a brain)

        ida = get_brain_by_path(a.root).id
        idb = get_brain_by_path(b.root).id

        brains.set_active_brain(ida)
        assert brains.resolve_active().id == ida
        from llmwiki.core.paths import load_active_brain

        assert load_active_brain().root == a.root

        # switch via the registry (as the API/front would) → CLI resolver follows
        brains.set_active_brain(idb)
        assert load_active_brain().root == b.root

    def test_resolve_active_self_heals_dead_active(self, tmp_path, monkeypatch) -> None:
        import shutil

        a = scaffold_service.init_brain(tmp_path / "live", git=False)
        dead = scaffold_service.init_brain(tmp_path / "dead", git=False)
        monkeypatch.delenv("WIKI_BRAIN", raising=False)
        dead_id = get_brain_by_path(dead.root).id
        brains.set_active_brain(dead_id)
        shutil.rmtree(dead.root)  # active brain's folder vanishes
        # resolver falls back to the live brain instead of raising
        assert brains.resolve_active().id == get_brain_by_path(a.root).id


class TestMigration:
    def test_migrates_legacy_db_into_uuid_dir(self, tmp_path) -> None:
        # register a fresh brain (empty uuid db)
        paths = scaffold_service.init_brain(tmp_path / "mybrain", git=False)
        brain = get_brain_by_path(paths.root)
        assert brain is not None

        # simulate pre-registry data at the legacy dirname-based location
        legacy_db = _paths_mod.WIKI_HOME / "brains" / "mybrain" / "metadata.db"
        _seed_legacy_source(legacy_db, "raw/articles/old.md")

        # uuid db is empty → migration should copy the legacy source in
        assert migrate_legacy_data(brain.id, brain.path) is True
        uuid_db = brains.get_brain_db_path(brain.id)
        conn = sqlite3.connect(uuid_db)
        n = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        conn.close()
        assert n == 1

    def test_does_not_clobber_nonempty_uuid_db(self, tmp_path) -> None:
        paths = scaffold_service.init_brain(tmp_path / "brain2", git=False)
        brain = get_brain_by_path(paths.root)
        # put a source directly in the uuid db (non-empty)
        uuid_db = brains.get_brain_db_path(brain.id)
        _seed_legacy_source(uuid_db.parent / "tmp.db", "x")  # build a seeded db
        (uuid_db.parent / "tmp.db").replace(uuid_db)
        # legacy also has data, but uuid is non-empty → no migration
        legacy_db = _paths_mod.WIKI_HOME / "brains" / "brain2" / "metadata.db"
        _seed_legacy_source(legacy_db, "raw/other.md")
        assert migrate_legacy_data(brain.id, brain.path) is False
