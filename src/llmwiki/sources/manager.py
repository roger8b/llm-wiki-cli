"""Source Manager: registra fontes brutas em ``raw/`` (imutáveis)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from ..core.markdown import extract_title
from ..core.misc import sha256
from ..core.models import Source, SourceStatus
from ..core.paths import BrainPaths
from ..db.repo import SourceRepo
from .extractors import extract_text, source_type

# Subpasta de raw/ por tipo de fonte.
_SUBDIR = {"md": "articles", "text": "articles", "pdf": "pdfs", "html": "articles"}


class AddResult:
    def __init__(self, source: Source, copied: bool, already_present: bool) -> None:
        self.source = source
        self.copied = copied
        self.already_present = already_present


def add_source(file: Path, paths: BrainPaths, repo: SourceRepo) -> AddResult:
    """Copia o arquivo para ``raw/<subdir>/`` (se ainda não estiver lá) e registra
    a fonte no banco. Dedup por hash de conteúdo.
    """
    file = file.resolve()
    content = file.read_bytes()
    digest = sha256(content)
    stype = source_type(file)

    existing = repo.get_by_hash(digest)
    if existing is not None:
        return AddResult(existing, copied=False, already_present=True)

    subdir = _SUBDIR.get(stype, "articles")
    dest_dir = paths.raw / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.name

    copied = False
    if file.parent.resolve() != dest_dir.resolve():
        shutil.copy2(file, dest)
        copied = True
    else:
        dest = file

    rel = paths.relative(dest)
    title = None
    if stype in ("md", "text"):
        try:
            title = extract_title(extract_text(dest))
        except Exception:
            title = None

    source = Source(
        path=rel,
        type=stype,
        title=title,
        hash=digest,
        added_at=datetime.now(UTC),
        status=SourceStatus.pending,
    )
    source = repo.upsert(source)
    return AddResult(source, copied=copied, already_present=False)
