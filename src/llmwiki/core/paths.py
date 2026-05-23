"""Brain path resolution.

Rules:
- Never hardcode brain paths — always derive from a discovered root.
- For user input: try the absolute path first; fall back to
  ``brain_root / user_input`` if the absolute path doesn't exist.

Layout
------
Inside the brain directory (git-tracked content):
  <brain>/wiki/          — LLM-written knowledge pages
  <brain>/raw/           — immutable raw sources
  <brain>/schemas/       — YAML page schemas
  <brain>/.llmwiki/      — marker dir (brain identity, tracked by git)

Global data directory (never committed):
  ~/.wiki/config.yaml           — global default config (model, fts_limit)
  ~/.wiki/brains/<id>/         — per-brain metadata, indexed by brain UUID
    metadata.db                 — SQLite knowledge index
    change_requests/            — staged diffs waiting for apply/reject
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import PathOutsideBrainError

if TYPE_CHECKING:
    from .brains import BrainInfo

# Global home for config + per-brain databases/CRs.
WIKI_HOME = Path.home() / ".wiki"


@dataclass(frozen=True)
class BrainPaths:
    """Canonical paths derived from the brain root."""

    root: Path
    brain_id: str | None = field(default=None, kw_only=True)

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def wiki(self) -> Path:
        return self.root / "wiki"

    @property
    def schemas(self) -> Path:
        return self.root / "schemas"

    @property
    def dot(self) -> Path:
        """Marker directory inside the brain (tracked by git, stays empty)."""
        return self.root / ".llmwiki"

    # ------------------------------------------------------------------
    # Global paths (live in ~/.wiki, never committed to the brain repo)
    # ------------------------------------------------------------------

    @property
    def global_dot(self) -> Path:
        """Per-brain data dir inside the global home (~/.wiki/brains/<id>/)."""
        if self.brain_id:
            return WIKI_HOME / "brains" / self.brain_id
        # Fallback: use dirname (backward compat for old structure)
        return WIKI_HOME / "brains" / self.root.resolve().name

    @property
    def db_path(self) -> Path:
        return self.global_dot / "metadata.db"

    @property
    def change_requests(self) -> Path:
        return self.global_dot / "change_requests"

    @property
    def index_path(self) -> Path:
        return self.wiki / "index.md"

    @property
    def log_path(self) -> Path:
        return self.wiki / "log.md"

    def relative(self, target: Path) -> str:
        """Caminho de ``target`` relativo à raiz do brain, com barras POSIX."""
        return target.resolve().relative_to(self.root.resolve()).as_posix()


def load_active_brain() -> BrainPaths:
    """Resolve the active brain (registry/env, with self-heal) → BrainPaths.

    Canonical entry point used by the CLI, MCP and API so all channels share
    the same active brain. Raises BrainNotFoundError if none is usable.
    """
    from .brains import resolve_active

    return load_brain_for_info(resolve_active())


def load_brain_for_info(brain: BrainInfo) -> BrainPaths:
    """Create BrainPaths from a BrainInfo object."""
    from .brains import get_brain_global_dir, migrate_legacy_data

    # Verify the brain's global dir exists or create it
    global_dir = get_brain_global_dir(brain.id)
    global_dir.mkdir(parents=True, exist_ok=True)
    (global_dir / "change_requests").mkdir(parents=True, exist_ok=True)
    # One-time migration: pull data from the old dirname-based dir if the UUID
    # dir is still empty (pre-registry brains had their db orphaned there).
    migrate_legacy_data(brain.id, brain.path)
    return BrainPaths(root=Path(brain.path), brain_id=brain.id)


def resolve_input(user_input: str, brain_root: Path) -> Path:
    """Resolve uma entrada de caminho do usuário.

    Tenta o caminho absoluto/relativo ao cwd; se não existir, cai para
    ``brain_root / user_input``. Garante que o resultado fica dentro do brain.
    """
    direct = Path(user_input).resolve()
    chosen = direct if direct.exists() else (brain_root / user_input).resolve()

    root = brain_root.resolve()
    if root not in (chosen, *chosen.parents):
        raise PathOutsideBrainError(
            f"Caminho '{user_input}' resolve para fora do brain ({chosen})."
        )
    return chosen