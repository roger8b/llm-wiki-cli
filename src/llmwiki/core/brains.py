"""Brain registry — single source of truth for brain configuration.

The brain registry lives in ``~/.wiki/config.yaml`` (shared with workspace config):

```yaml
activeBrainId: "uuid-v4"
brains:
  - id: "uuid-v4"
    name: "my-wiki"
    path: "/Users/roger/wiki/my-wiki"
    icon: "brain"
    createdAt: "2026-05-23T10:00:00Z"
```

The database (metadata.db) remains at ``~/.wiki/brains/<id>/metadata.db``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from . import paths as _paths_mod
from .errors import BrainNotFoundError, WikiError

if TYPE_CHECKING:
    from .paths import BrainPaths

# Markers that identify the root of a brain.
_MARKERS = (".llmwiki", "wiki")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BrainAlreadyRegisteredError(WikiError):
    """A brain with this path is already registered."""


class BrainNotValidError(WikiError):
    """The path does not contain a valid brain structure."""


# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------


def _brains_dir() -> Path:
    # Reference WIKI_HOME via the paths module so tests can monkeypatch it.
    return _paths_mod.WIKI_HOME / "brains"


def _config_path() -> Path:
    return _paths_mod.WIKI_HOME / "config.yaml"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class BrainInfo:
    """Represents a registered brain."""

    __slots__ = ("id", "name", "path", "icon", "createdAt")

    def __init__(
        self,
        id: str,
        name: str,
        path: str,
        icon: str = "brain",
        createdAt: str | None = None,
    ):
        self.id = id
        self.name = name
        self.path = path
        self.icon = icon
        self.createdAt = createdAt or datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "icon": self.icon,
            "createdAt": self.createdAt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrainInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            icon=data.get("icon", "brain"),
            createdAt=data.get("createdAt"),
        )


# ---------------------------------------------------------------------------
# Config file I/O
# ---------------------------------------------------------------------------


def _load_config() -> dict[str, Any]:
    """Load config.yaml."""
    cfg = _config_path()
    if cfg.exists():
        try:
            data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (yaml.YAMLError, OSError):
            pass
    return {}


def _save_config(data: dict[str, Any]) -> None:
    """Write config.yaml atomically."""
    cfg = _config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(cfg)


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def list_brains() -> list[BrainInfo]:
    """Return all registered brains."""
    data = _load_config()
    brains_data = data.get("brains", [])
    return [BrainInfo.from_dict(b) for b in brains_data]


def get_brain(id: str) -> BrainInfo | None:
    """Return a brain by ID, or None if not found."""
    brains = list_brains()
    return next((b for b in brains if b.id == id), None)


def get_active_brain() -> BrainInfo | None:
    """Return the currently active brain, or None."""
    data = _load_config()
    active_id = data.get("activeBrainId")
    if not active_id:
        return None
    return get_brain(active_id)


def is_brain_dir(path: str | Path) -> bool:
    """True if ``path`` contains a brain marker (.llmwiki or wiki/).

    Single source of truth for "is this a brain folder?" — reused by the API
    deps, path loader and scaffold instead of duplicating the check.
    """
    p = Path(path)
    return any((p / m).is_dir() for m in _MARKERS)


def get_brain_by_path(path: str | Path) -> BrainInfo | None:
    """Return the registered brain at ``path`` (resolved), or None."""
    target = str(Path(path).resolve())
    return next((b for b in list_brains() if b.path == target), None)


def validate_brain_path(path: str | Path) -> tuple[bool, str]:
    """Validate that a path contains a valid brain structure.

    Returns (is_valid, message).
    """
    p = Path(path).resolve()
    if not p.exists():
        return False, f"Path does not exist: {p}"
    if not p.is_dir():
        return False, f"Path is not a directory: {p}"
    if not is_brain_dir(p):
        return False, f"No brain marker (.llmwiki or wiki/) found in: {p}"
    return True, "valid"


def add_brain(
    name: str,
    path: str,
    icon: str = "brain",
    *,
    activate: bool = False,
) -> BrainInfo:
    """Register a new brain.

    Validates the path, checks for duplicates, and saves to config.yaml.
    """
    path_obj = Path(path).resolve()

    # Validate
    valid, msg = validate_brain_path(path_obj)
    if not valid:
        raise BrainNotValidError(msg)

    # Check duplicate path
    existing = get_brain_by_path(path_obj)
    if existing:
        raise BrainAlreadyRegisteredError(
            f"Brain already registered at {path_obj} (id={existing.id}, name={existing.name})"
        )

    # Create brain info
    brain = BrainInfo(
        id=str(uuid.uuid4()),
        name=name,
        path=str(path_obj),
        icon=icon,
    )

    # Load, append, save
    data = _load_config()
    brains: list[dict[str, Any]] = list(data.get("brains", []))
    brains.append(brain.to_dict())
    data["brains"] = brains

    if activate or not data.get("activeBrainId"):
        data["activeBrainId"] = brain.id

    _save_config(data)

    # Create global data directory for this brain
    global_dir = _brains_dir() / brain.id
    global_dir.mkdir(parents=True, exist_ok=True)
    (global_dir / "change_requests").mkdir(parents=True, exist_ok=True)

    return brain


def update_brain(id: str, updates: dict[str, Any]) -> BrainInfo:
    """Update a brain's name, path, or icon."""
    data = _load_config()
    brains: list[dict[str, Any]] = list(data.get("brains", []))
    brain_data = None
    for b in brains:
        if b["id"] == id:
            brain_data = b
            break

    if not brain_data:
        raise BrainNotFoundError(f"Brain not found: {id}")

    if "path" in updates:
        path_obj = Path(updates["path"]).resolve()
        valid, msg = validate_brain_path(path_obj)
        if not valid:
            raise BrainNotValidError(msg)
        clash = get_brain_by_path(path_obj)
        if clash and clash.id != id:
            raise BrainAlreadyRegisteredError(
                f"Path already used by brain '{clash.name}' ({clash.id})"
            )
        brain_data["path"] = str(path_obj)

    if "name" in updates:
        brain_data["name"] = updates["name"]

    if "icon" in updates:
        brain_data["icon"] = updates["icon"]

    data["brains"] = brains
    _save_config(data)
    return BrainInfo.from_dict(brain_data)


def remove_brain(id: str) -> BrainInfo | None:
    """Remove a brain by ID.

    If the brain is the active one, auto-selects the first remaining brain.
    Returns the removed brain info. Fails if it's the last brain.
    """
    data = _load_config()
    brains: list[dict[str, Any]] = list(data.get("brains", []))
    removed = None
    for i, b in enumerate(brains):
        if b["id"] == id:
            removed = brains.pop(i)
            break

    if not removed:
        raise BrainNotFoundError(f"Brain not found: {id}")

    if len(brains) == 0:
        raise WikiError("Cannot delete the last brain. Register another one first.")

    data["brains"] = brains

    if data.get("activeBrainId") == id:
        data["activeBrainId"] = brains[0]["id"]

    _save_config(data)

    # Optionally remove global data dir (comment out to preserve on delete)
    # _remove_brain_global_dir(id)

    return BrainInfo.from_dict(removed)


def set_active_brain(id: str) -> BrainInfo:
    """Set the active brain by ID."""
    brain = get_brain(id)
    if not brain:
        raise BrainNotFoundError(f"Brain not found: {id}")

    data = _load_config()
    data["activeBrainId"] = id
    _save_config(data)

    return brain


def register_or_get(
    path: str | Path, name: str | None = None, *, activate: bool = True
) -> BrainInfo:
    """Return the registered brain for ``path``, registering it if absent.

    Keeps env-based / CLI access in sync with the registry so the UI always
    sees the brain being served.
    """
    p = Path(path).resolve()
    existing = get_brain_by_path(p)
    if existing:
        active = get_active_brain()
        if activate and (active is None or active.id != existing.id):
            set_active_brain(existing.id)
        return existing
    return add_brain(name or p.name, str(p), activate=activate)


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------


def get_active_brain_path() -> Path:
    """Return the filesystem path of the active brain.

    Raises BrainNotFoundError if no brain is registered or active.
    """
    brain = get_active_brain()
    if not brain:
        raise BrainNotFoundError(
            "No active brain. Use POST /api/brains/active to set one."
        )
    return Path(brain.path)


def get_paths_for_brain(brain_or_id: BrainInfo | str) -> BrainPaths:
    """Return BrainPaths for a given BrainInfo or brain ID."""
    from .paths import BrainPaths

    if isinstance(brain_or_id, str):
        brain = get_brain(brain_or_id)
        if not brain:
            raise BrainNotFoundError(f"Brain not found: {brain_or_id}")
    else:
        brain = brain_or_id
    return BrainPaths(root=Path(brain.path), brain_id=brain.id)


# ---------------------------------------------------------------------------
# Global data directory (uses brain ID, not dirname)
# ---------------------------------------------------------------------------


def get_brain_global_dir(brain_id: str) -> Path:
    """Get the global data directory for a brain by its ID."""
    return _brains_dir() / brain_id


def get_brain_db_path(brain_id: str) -> Path:
    """Get the SQLite database path for a brain by its ID."""
    return get_brain_global_dir(brain_id) / "metadata.db"


def _db_is_empty(db: Path) -> bool:
    """True if the db is absent or has no sources and no wiki pages."""
    import sqlite3

    if not db.exists():
        return True
    try:
        conn = sqlite3.connect(db)
        n = conn.execute(
            "SELECT (SELECT COUNT(*) FROM sources) + (SELECT COUNT(*) FROM wiki_pages)"
        ).fetchone()[0]
        conn.close()
        return n == 0
    except sqlite3.Error:
        return True


def migrate_legacy_data(brain_id: str, brain_path: str | Path) -> bool:
    """Migrate a brain's data from the old dirname-based dir to its UUID dir.

    Before the registry, per-brain data lived at ~/.wiki/brains/<dirname>/.
    Now it lives at ~/.wiki/brains/<id>/. Brains created back then have their
    db (sources, pages, change requests) orphaned in the old location, so the
    UI shows nothing. This copies the legacy db into the UUID dir — but only
    when the UUID db is still empty, to never clobber newer data.

    Returns True if a migration happened.
    """
    import shutil

    legacy_dir = _brains_dir() / Path(brain_path).name
    uuid_dir = get_brain_global_dir(brain_id)
    legacy_db = legacy_dir / "metadata.db"
    uuid_db = uuid_dir / "metadata.db"

    if not legacy_db.exists() or legacy_dir.resolve() == uuid_dir.resolve():
        return False
    if not _db_is_empty(uuid_db):
        return False  # UUID dir already has data — don't overwrite
    if _db_is_empty(legacy_db):
        return False  # nothing worth migrating

    uuid_dir.mkdir(parents=True, exist_ok=True)
    # The UUID db is empty (guard above) — overwrite it with the legacy db.
    shutil.copy2(legacy_db, uuid_db)
    # Copy any other legacy assets (change_requests/, stray files) that aren't
    # already present in the UUID dir.
    for item in legacy_dir.iterdir():
        if item.name == "metadata.db":
            continue
        target = uuid_dir / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return True