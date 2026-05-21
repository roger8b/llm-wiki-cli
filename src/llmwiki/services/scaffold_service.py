"""Cria a estrutura de um novo brain (usado por ``llmwiki init``)."""

from __future__ import annotations

import subprocess
from importlib import resources
from pathlib import Path

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
# (arquivo de template, destino relativo à raiz do brain)
_TEMPLATE_FILES = {
    "AGENTS.md": "schemas/AGENTS.md",
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
    """Cria toda a árvore do brain. Levanta ``BrainExistsError`` se já existir."""
    root = root.resolve()
    paths = BrainPaths(root=root)

    if paths.dot.exists() and not force:
        raise BrainExistsError(f"Já existe um brain em {root} (use --force).")

    for sub in _RAW_SUBDIRS:
        (paths.raw / sub).mkdir(parents=True, exist_ok=True)
    for sub in _WIKI_SUBDIRS:
        (paths.wiki / sub).mkdir(parents=True, exist_ok=True)
    paths.schemas.mkdir(parents=True, exist_ok=True)
    (paths.schemas / "page_templates").mkdir(parents=True, exist_ok=True)
    paths.dot.mkdir(parents=True, exist_ok=True)
    paths.change_requests.mkdir(parents=True, exist_ok=True)

    for name, rel in _TEMPLATE_FILES.items():
        _copy_template(name, root / rel)
    for name in _PAGE_TEMPLATES:
        _copy_template(f"page_templates/{name}", paths.schemas / "page_templates" / name)

    if not paths.index_path.exists():
        paths.index_path.write_text(
            "# Índice da Wiki\n\n_Nenhuma página ainda._\n", encoding="utf-8"
        )
    if not paths.log_path.exists():
        paths.log_path.write_text(
            f"# Log da Wiki\n\n- {today()}: brain inicializado.\n", encoding="utf-8"
        )

    write_default_config(paths)
    # Cria o banco (schema aplicado na conexão).
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
            ".llmwiki/cache/\n.llmwiki/embeddings/\n", encoding="utf-8"
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Git ausente não deve quebrar o init.
        pass
