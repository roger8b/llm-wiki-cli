"""Parallel chunk passes for long-source ingestion (#277).

Chunk passes run on isolated backends and are merged deterministically (highest
chunk index wins a path collision, mirroring serial overwrite order), so a long
source ingests in a fraction of the serial time while producing a CR identical
to the serial run regardless of thread scheduling.
"""

from __future__ import annotations

import pytest
from test_ingest_multipass import _long_source, _outline_runner

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.errors import JobCancelledError
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import JobRepo
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import change_request_service, ingest_service


def _cfg(brain: BrainPaths, concurrency: int) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root, ingest_chunk_concurrency=concurrency)


def _distinct_runner(cfg, backend, *, source_path, source_text, source_meta=None,
                     outline=None, part=None, **kw):
    """Each chunk stages a page unique to its part — no collisions."""
    idx = part[0] if part else 1
    path = f"wiki/concepts/part-{idx}.md"
    backend.write(path, f"---\ntitle: Part {idx}\ntype: concept\n---\n# Part {idx}\nbody\n")
    return IngestionResult(summary=f"part {idx}", new_pages=[path])


class _CollidingRunner:
    """Every chunk stages the SAME path, tagged with its chunk index."""

    def __call__(self, cfg, backend, *, source_path, source_text, source_meta=None,
                 outline=None, part=None, **kw):
        idx = part[0] if part else 1
        backend.write(
            "wiki/concepts/shared.md",
            f"---\ntitle: Shared\ntype: concept\n---\n# Shared\nfrom chunk {idx}\n",
        )
        return IngestionResult(summary=f"part {idx}", new_pages=["wiki/concepts/shared.md"])


# Slug variants of ONE concept, cycled across chunks. Same page, different
# casing/spacing — exactly what parallel chunks produced for the Voyager paper
# (#301): "exploreUntil primitive" / "exploreUntil-primitive" / "exploreuntil-primitive".
_SLUG_VARIANTS = [
    "exploreUntil primitive",
    "exploreUntil-primitive",
    "exploreuntil-primitive",
]


class _VariantSlugRunner:
    """Every chunk stages the same concept under a different slug variant."""

    def __call__(self, cfg, backend, *, source_path, source_text, source_meta=None,
                 outline=None, part=None, **kw):
        idx = part[0] if part else 1
        stem = _SLUG_VARIANTS[idx % len(_SLUG_VARIANTS)]
        path = f"wiki/concepts/{stem}.md"
        backend.write(
            path,
            f"---\ntitle: exploreUntil primitive\ntype: concept\n---\n"
            f"# exploreUntil primitive\nfrom chunk {idx}\n",
        )
        return IngestionResult(summary=f"part {idx}", new_pages=[path])


def _ingest(brain: BrainPaths, cfg: WorkspaceConfig, runner, **kw):
    conn = get_connection(brain.db_path)
    try:
        return ingest_service.ingest(
            _long_source(brain), brain, conn, cfg,
            runner=runner, outline_runner=_outline_runner, **kw,
        )
    finally:
        conn.close()


class TestParallelMerge:
    def test_distinct_pages_all_merged(self, brain: BrainPaths) -> None:
        cr = _ingest(brain, _cfg(brain, 3), _distinct_runner)
        paths = sorted(c.path for c in cr.changes)
        # One page per chunk part, all distinct, none lost in the merge.
        assert paths == sorted(set(paths))
        assert all(p.startswith("wiki/concepts/part-") for p in paths)
        assert len(paths) >= 2  # the long source splits into multiple chunks

    def test_collision_resolved_deterministically(self, brain: BrainPaths, tmp_path) -> None:
        # All chunks wrote the same path -> exactly one page survives the merge.
        cr = _ingest(brain, _cfg(brain, 3), _CollidingRunner())
        assert [c.path for c in cr.changes] == ["wiki/concepts/shared.md"]
        # Deterministic: a second parallel run yields byte-identical content.
        from llmwiki.services import scaffold_service

        brain2 = scaffold_service.init_brain(tmp_path / "brain2", git=False)
        cr2 = _ingest(brain2, _cfg(brain2, 3), _CollidingRunner())
        assert cr.changes[0].new_content == cr2.changes[0].new_content

    def test_slug_variants_collapse_to_one_canonical_page(self, brain: BrainPaths) -> None:
        # Chunks named the same concept "exploreUntil primitive" /
        # "exploreUntil-primitive" / "exploreuntil-primitive". Path-string dedup
        # missed them; slug-canonical dedup (#301) collapses to one clean page.
        cr = _ingest(brain, _cfg(brain, 3), _VariantSlugRunner())
        assert [c.path for c in cr.changes] == ["wiki/concepts/exploreuntil-primitive.md"]
        # No space/uppercase variant leaked into the CR.
        for change in cr.changes:
            assert change.path == change.path.lower()
            assert " " not in change.path

    def test_parallel_matches_serial(self, brain: BrainPaths, tmp_path) -> None:
        serial = _ingest(brain, _cfg(brain, 1), _CollidingRunner())
        # Fresh brain for the parallel run so staging/CR state doesn't carry over.
        from llmwiki.services import scaffold_service

        brain2 = scaffold_service.init_brain(tmp_path / "brain2", git=False)
        parallel = _ingest(brain2, _cfg(brain2, 4), _CollidingRunner())
        assert [c.path for c in serial.changes] == [c.path for c in parallel.changes]
        assert serial.changes[0].new_content == parallel.changes[0].new_content


class TestParallelCancellation:
    def test_cancel_before_passes_creates_no_cr(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            jid = JobRepo(conn).create("ingest", status="running")
            with pytest.raises(JobCancelledError):
                ingest_service.ingest(
                    _long_source(brain), brain, conn, _cfg(brain, 3),
                    runner=_distinct_runner, outline_runner=_outline_runner,
                    job_id=jid, cancel_check=lambda: True,
                )
            assert JobRepo(conn).get(jid)["status"] == "cancelled"
            assert change_request_service.list_crs(conn) == []
        finally:
            conn.close()


def test_config_field_default_is_three() -> None:
    cfg = WorkspaceConfig(brain_root=BrainPaths(root="/tmp/x").root)
    assert cfg.ingest_chunk_concurrency == 3


class TestCanonicalStagingPath:
    def test_case_space_and_hyphen_variants_share_one_key(self) -> None:
        from llmwiki.services.ingest_service import _canonical_staging_path

        canonical = "wiki/concepts/exploreuntil-primitive.md"
        for variant in (
            "wiki/concepts/exploreUntil primitive.md",
            "wiki/concepts/exploreUntil-primitive.md",
            "wiki/concepts/exploreuntil-primitive.md",
        ):
            assert _canonical_staging_path(variant) == canonical

    def test_directory_prevents_cross_type_merge(self) -> None:
        from llmwiki.services.ingest_service import _canonical_staging_path

        assert _canonical_staging_path("wiki/concepts/voyager.md") != _canonical_staging_path(
            "wiki/research/voyager.md"
        )

    def test_empty_slug_falls_back_to_original(self) -> None:
        from llmwiki.services.ingest_service import _canonical_staging_path

        assert _canonical_staging_path("wiki/concepts/---.md") == "wiki/concepts/---.md"


def test_merge_results_canonicalizes_declared_paths() -> None:
    # Declared paths (new_pages/affected_pages) must fold onto the canonical slug
    # so the audit compares like-for-like with the canonical staged paths (#301).
    from llmwiki.llm_agents.models import IngestionResult
    from llmwiki.services.ingest_service import _merge_results

    merged = _merge_results(
        [
            IngestionResult(summary="a", new_pages=["wiki/concepts/exploreUntil primitive.md"]),
            IngestionResult(summary="b", new_pages=["wiki/concepts/exploreUntil-primitive.md"]),
        ]
    )
    assert merged.new_pages == ["wiki/concepts/exploreuntil-primitive.md"]
