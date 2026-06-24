"""Pre-fetch of outline candidates before the chunk passes (#292).

The outline already lists a source's concepts, so one hybrid search per concept
runs IN CODE and the result is injected into each chunk's message — cutting the
sequential ``search_pages``/``related_pages`` tool round-trips the agent used to
spend discovering existing pages.
"""

from __future__ import annotations

from pathlib import Path

from llmwiki.core.config import WorkspaceConfig
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents import factory
from llmwiki.llm_agents.models import OutlinePlan
from llmwiki.services import index_service, ingest_service


def _seed_cfg(tmp_path: Path, titles: list[str]) -> WorkspaceConfig:
    """Build a brain whose db_path matches ``WorkspaceConfig.paths`` (root-based,
    as in production) and index ``titles`` into it."""
    cfg = WorkspaceConfig(brain_root=tmp_path / "brain")
    paths = cfg.paths
    concepts_dir = paths.wiki / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    for title in titles:
        slug = title.lower().replace(" ", "-")
        (concepts_dir / f"{slug}.md").write_text(
            f"---\ntitle: {title}\ntype: concept\nconfidence: high\n---\n\n"
            f"# {title}\n\nThis page explains {title} in detail.\n",
            encoding="utf-8",
        )
    conn = get_connection(paths.db_path)
    try:
        index_service.reindex(paths, conn, cfg)
        conn.commit()  # persist so prefetch's own connection sees the pages
    finally:
        conn.close()
    return cfg


class TestPrefetchCandidates:
    def setup_method(self) -> None:
        factory.reset_prefetch_cache()

    def test_finds_existing_pages_for_concepts(self, tmp_path: Path) -> None:
        cfg = _seed_cfg(tmp_path, ["Vector Store", "Embedding Model"])
        out = factory.prefetch_candidates(
            cfg, ["Vector Store", "Embedding Model"], limit=3
        )
        assert out["Vector Store"], "expected a hit for an indexed concept"
        assert any(c["path"].endswith("vector-store.md") for c in out["Vector Store"])

    def test_limit_zero_disables(self, tmp_path: Path) -> None:
        cfg = _seed_cfg(tmp_path, ["Vector Store"])
        assert factory.prefetch_candidates(cfg, ["Vector Store"], limit=0) == {}

    def test_empty_brain_returns_empty(self, tmp_path: Path) -> None:
        cfg = WorkspaceConfig(brain_root=tmp_path / "brain")
        # No DB file / no pages → nothing to prefetch, never raises.
        assert factory.prefetch_candidates(cfg, ["Anything"], limit=3) == {}


class TestCandidatesInMessage:
    def test_chunk_context_renders_candidates(self) -> None:
        outline = OutlinePlan(concepts=["Vector Store"], summary="s")
        candidates = {"Vector Store": [{"path": "wiki/concepts/vector-store.md",
                                        "title": "Vector Store", "score": 0.9}]}
        msg = factory._chunk_context(outline, (2, 3), candidates)
        assert "PÁGINAS EXISTENTES RELACIONADAS" in msg
        assert "wiki/concepts/vector-store.md" in msg

    def test_chunk_context_without_candidates_has_no_block(self) -> None:
        outline = OutlinePlan(concepts=["Vector Store"], summary="s")
        msg = factory._chunk_context(outline, (2, 3), None)
        assert "PÁGINAS EXISTENTES RELACIONADAS" not in msg

    def test_all_zero_hit_concepts_suppress_block(self) -> None:
        # Concepts present but each with an empty candidate list → no header.
        msg = factory._chunk_context(
            OutlinePlan(concepts=["X"], summary="s"), (1, 2), {"X": []}
        )
        assert "PÁGINAS EXISTENTES RELACIONADAS" not in msg

    def test_ingestion_message_includes_candidates(self, tmp_path: Path) -> None:
        cfg = WorkspaceConfig(brain_root=tmp_path)
        candidates = {"Vector Store": [{"path": "wiki/concepts/vector-store.md",
                                        "title": "Vector Store", "score": 0.9}]}
        msg = factory._ingestion_message(
            cfg, source_path="raw/x.md", source_text="t",
            outline=OutlinePlan(concepts=["Vector Store"], summary="s"),
            part=(1, 2), candidates=candidates,
        )
        assert "wiki/concepts/vector-store.md" in msg

    def test_chunk_context_can_label_scoped_concepts(self) -> None:
        msg = factory._chunk_context(
            OutlinePlan(concepts=["Vector Store"], summary="s"),
            (1, 2),
            scoped_concepts=True,
        )
        assert "CONCEITOS DESTE TRECHO: Vector Store" in msg
        assert "plano global" not in msg


class TestScopedConcepts:
    def test_maps_concepts_to_matching_chunks(self) -> None:
        outlines = ingest_service._scoped_outlines(
            OutlinePlan(concepts=["Vector Store", "Embedding Model"], summary="s"),
            ["intro about vector-store", "details about embedding model"],
        )
        assert [o.concepts for o in outlines] == [["Vector Store"], ["Embedding Model"]]

    def test_unmatched_concept_falls_back_to_all_chunks(self) -> None:
        outlines = ingest_service._scoped_outlines(
            OutlinePlan(concepts=["Vector Store", "No Match"], summary="s"),
            ["vector store first", "other chunk"],
        )
        assert [o.concepts for o in outlines] == [
            ["Vector Store", "No Match"],
            ["No Match"],
        ]

    def test_multi_chunk_concept_stays_in_each_matching_chunk(self) -> None:
        outlines = ingest_service._scoped_outlines(
            OutlinePlan(concepts=["Shared Term"], summary="s"),
            ["shared term here", "shared-term again"],
        )
        assert [o.concepts for o in outlines] == [["Shared Term"], ["Shared Term"]]
