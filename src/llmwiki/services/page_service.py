"""Criação de páginas da wiki a partir de templates (determinístico)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from ..core.errors import PageExistsError
from ..core.markdown import slugify
from ..core.misc import today
from ..core.models import PageType
from ..core.paths import BrainPaths

# Tipo de página → subdiretório em wiki/.
_DIR = {
    PageType.concept: "concepts",
    PageType.entity: "entities",
    PageType.source_summary: "research",
    PageType.synthesis: "synthesis",
    PageType.decision: "decisions",
    PageType.project: "projects",
    PageType.research: "research",
}


def _template(page_type: PageType) -> str:
    return (
        resources.files("llmwiki")
        .joinpath("templates", "page_templates", f"{page_type.value}.md")
        .read_text(encoding="utf-8")
    )


def create_page(
    title: str, page_type: PageType, paths: BrainPaths
) -> Path:
    """Cria uma nova página a partir do template do tipo. Retorna o caminho criado."""
    slug = slugify(title)
    dest = paths.wiki / _DIR[page_type] / f"{slug}.md"
    if dest.exists():
        raise PageExistsError(f"Página já existe: {paths.relative(dest)}")

    content = _template(page_type).replace("{{title}}", title).replace("{{today}}", today())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest
