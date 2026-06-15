"""Source Manager: registers raw sources in ``raw/`` (immutable)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from ..core import frontmatter
from ..core.errors import EmptyExtractionError, FetchError
from ..core.markdown import extract_title, slugify
from ..core.misc import sha256
from ..core.models import Source, SourceStatus
from ..core.paths import BrainPaths
from ..db.repo import SourceRepo
from .extractors import ExtractedSource, extract_text, source_type

# Extracted bodies shorter than this are almost certainly a paywall or a
# JavaScript-rendered shell rather than a real article (#195).
_MIN_URL_CONTENT_CHARS = 200

# Subfolder of raw/ by source type.
_SUBDIR = {"md": "articles", "text": "articles", "pdf": "pdfs", "html": "articles"}


class AddResult:
    def __init__(self, source: Source, copied: bool, already_present: bool) -> None:
        self.source = source
        self.copied = copied
        self.already_present = already_present


def add_source(file: Path, paths: BrainPaths, repo: SourceRepo) -> AddResult:
    """Copies the file to ``raw/<subdir>/`` (if not already there) and registers
    the source in the database. Dedup by content hash.
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


def fetch_and_extract_url(
    url: str, *, timeout: int | None = None
) -> ExtractedSource:
    """Download a URL and return its cleaned ``ExtractedSource`` (#195).

    Raises ``FetchError`` on a bad scheme or any download failure (404,
    timeout, network) and ``EmptyExtractionError`` when too little text comes
    back (paywall / JavaScript-rendered page). No disk writes — used by both
    ``add_url`` and the preview endpoint.
    """
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchError(f"Unsupported URL scheme in {url!r} (use http or https).")

    from .extractors.html import _load_trafilatura, extract_source_from_html

    trafilatura = _load_trafilatura()
    config = None
    if timeout:
        try:
            from trafilatura.settings import use_config

            config = use_config()
            config.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(timeout))
        except Exception:  # noqa: BLE001 — older trafilatura: fall back to default
            config = None
    try:
        html = (
            trafilatura.fetch_url(url, config=config)  # type: ignore[attr-defined]
            if config is not None
            else trafilatura.fetch_url(url)  # type: ignore[attr-defined]
        )
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Could not download {url}: {exc}") from exc
    if not html:
        raise FetchError(
            f"Could not download {url} (network error, 404, or timeout)."
        )

    extracted = extract_source_from_html(html, url)
    if len(extracted.text) < _MIN_URL_CONTENT_CHARS:
        raise EmptyExtractionError(
            f"Only {len(extracted.text)} characters extracted from {url} — "
            "likely a paywall or a JavaScript-rendered page."
        )
    return extracted


def _unique_path(dest_dir: Path, slug: str) -> Path:
    """``<slug>.md`` in ``dest_dir``, suffixing ``-2``, ``-3``… on collision."""
    candidate = dest_dir / f"{slug}.md"
    n = 2
    while candidate.exists():
        candidate = dest_dir / f"{slug}-{n}.md"
        n += 1
    return candidate


def add_url(
    url: str,
    paths: BrainPaths,
    repo: SourceRepo,
    *,
    timeout: int | None = None,
) -> AddResult:
    """Download a web article and register it as a source (#195).

    Persists the cleaned article to ``raw/web/<slug>.md`` with capture
    provenance in the frontmatter (url/title/captured_at/author?/date?) so the
    URL flows to the page ``sources`` at ingestion (#163). Dedup is by the hash
    of the written document — re-capturing the same content is a duplicate.
    """
    extracted = fetch_and_extract_url(url, timeout=timeout)
    captured_at = datetime.now(UTC)
    host = urlparse(url).netloc
    title = extracted.title or host or url
    meta: dict[str, str] = {
        "url": url,
        "title": title,
        "captured_at": captured_at.isoformat(),
    }
    if extracted.author:
        meta["author"] = extracted.author
    if extracted.date:
        meta["date"] = extracted.date

    content = frontmatter.dump(meta, extracted.text).encode("utf-8")
    # Dedup on the *extracted content*, not the document — the capture
    # timestamp in the frontmatter would otherwise make every fetch unique.
    digest = sha256(extracted.text)

    existing = repo.get_by_hash(digest)
    if existing is not None:
        return AddResult(existing, copied=False, already_present=True)

    dest_dir = paths.raw / "web"
    dest_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title) or slugify(host) or "page"
    dest = _unique_path(dest_dir, slug)
    dest.write_bytes(content)

    source = Source(
        path=paths.relative(dest),
        type="html",
        title=title,
        hash=digest,
        added_at=captured_at,
        status=SourceStatus.pending,
    )
    source = repo.upsert(source)
    return AddResult(source, copied=True, already_present=False)


def sync_sources(paths: BrainPaths, repo: SourceRepo) -> int:
    """Register any file in ``raw/`` that isn't yet in the sources table.

    ``raw/`` is the source of truth for sources, so this makes the listing
    reflect what's on disk regardless of db history (e.g. after a brain was
    registered or its db was reset). Returns the number newly registered.
    """
    raw = paths.raw
    if not raw.is_dir():
        return 0
    # Skip files already represented in the db (by relative path) so repeat
    # calls don't re-hash every file — only genuinely new files are processed.
    known = {s.path for s in repo.list()}
    added = 0
    for f in sorted(raw.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        if paths.relative(f) in known:
            continue
        result = add_source(f, paths, repo)
        if not result.already_present:
            added += 1
    return added
