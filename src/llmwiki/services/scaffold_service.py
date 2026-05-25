"""Creates the structure of a new brain (used by ``llmwiki init``)."""

from __future__ import annotations

import subprocess
from importlib import resources
from pathlib import Path

from ..core import brains as brains_registry
from ..core.config import write_default_config
from ..core.errors import BrainExistsError
from ..core.misc import today
from ..core.paths import BrainPaths
from ..db.connection import get_connection

_RAW_SUBDIRS = ("articles", "pdfs", "meetings", "slack", "images")
_WIKI_SUBDIRS = (
    "concepts",
    "entities",
    "projects",
    "decisions",
    "research",
    "synthesis",
)
# (template file, destination relative to the brain root)
# AGENTS.md and CLAUDE.md sit at the brain root so humans and agents (incl.
# Claude Code) auto-discover the operating contract on entry.
_TEMPLATE_FILES = {
    "AGENTS.md": "AGENTS.md",
    "CLAUDE.md": "CLAUDE.md",
    "WIKI_PROTOCOL.md": "WIKI_PROTOCOL.md",
    "wiki_schema.md": "schemas/wiki_schema.md",
}
_PAGE_TEMPLATES = (
    "concept.md",
    "entity.md",
    "source_summary.md",
    "synthesis.md",
    "decision.md",
    "project.md",
    "research.md",
)


def _copy_template(name: str, dest: Path) -> None:
    text = resources.files("llmwiki").joinpath("templates", name).read_text(
        encoding="utf-8"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def init_brain(root: Path, *, git: bool = True, force: bool = False) -> BrainPaths:
    """Creates the entire brain tree. Raises ``BrainExistsError`` if it already exists."""
    root = root.resolve()
    paths = BrainPaths(root=root)

    if paths.dot.exists() and not force:
        raise BrainExistsError(f"A brain already exists in {root} (use --force).")

    for sub in _RAW_SUBDIRS:
        (paths.raw / sub).mkdir(parents=True, exist_ok=True)
    for sub in _WIKI_SUBDIRS:
        (paths.wiki / sub).mkdir(parents=True, exist_ok=True)
    paths.schemas.mkdir(parents=True, exist_ok=True)
    (paths.schemas / "page_templates").mkdir(parents=True, exist_ok=True)
    # .llmwiki/ is a git-tracked marker directory (stays empty in the brain repo)
    paths.dot.mkdir(parents=True, exist_ok=True)

    for name, rel in _TEMPLATE_FILES.items():
        _copy_template(name, root / rel)
    for name in _PAGE_TEMPLATES:
        _copy_template(f"page_templates/{name}", paths.schemas / "page_templates" / name)

    if not paths.index_path.exists():
        paths.index_path.write_text(
            "# Wiki Index\n\n_No pages yet._\n", encoding="utf-8"
        )
    if not paths.log_path.exists():
        paths.log_path.write_text(
            f"# Wiki Log\n\n- {today()}: brain initialized.\n", encoding="utf-8"
        )

    # Seed the global config defaults (model, fts_limit…) before registering,
    # so config.yaml carries them alongside the brain registry entry.
    write_default_config(paths)

    # Register in the brain registry (single source of truth). This assigns a
    # UUID and creates the per-brain global data dir (~/.wiki/brains/<id>/).
    # The .llmwiki marker already exists, so validation passes.
    brain = brains_registry.register_or_get(root, name=root.name, activate=True)
    paths = BrainPaths(root=root, brain_id=brain.id)

    # Create the SQLite db in the brain's global dir (schema applied on connect).
    get_connection(paths.db_path).close()

    if git:
        _git_init(root)

    return paths


def _git_init(root: Path) -> None:
    if (root / ".git").exists():
        return
    try:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        (root / ".gitignore").write_text(
            "# llm-wiki: brain content is tracked; metadata lives in ~/.wiki/\n",
            encoding="utf-8",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Missing Git should not break init.
        pass
