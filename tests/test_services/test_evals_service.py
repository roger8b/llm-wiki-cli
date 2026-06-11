"""Tests for the evals harness (issue #175) — fake runner, no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.core import frontmatter
from llmwiki.core.config import WorkspaceConfig
from llmwiki.llm_agents.backend import ChangeRequestBackend
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import evals_service

DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset"


def _page(title: str, ptype: str, body: str) -> str:
    return frontmatter.dump(
        {"title": title, "type": ptype, "confidence": "high"}, body
    )


def _fake_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
) -> IngestionResult:
    """Deterministic stand-in for the ingestion agent.

    Mirrors what a competent agent would do per dataset case, except case 04
    where it deliberately creates a DUPLICATE so the harness can detect it.
    """
    name = Path(source_path).name
    new_pages: list[str] = []

    def w(path: str, title: str, ptype: str, body: str) -> None:
        backend.write(path, _page(title, ptype, body))
        new_pages.append(path)

    if name.startswith("01"):
        w("wiki/concepts/vector-embeddings.md", "Vector Embeddings", "concept",
          "A dense numeric representation of meaning.")
    elif name.startswith("02"):
        w("wiki/concepts/retrieval-augmented-generation.md",
          "Retrieval-Augmented Generation", "concept",
          "Grounds answers using a [[Vector Database]] and [[Embeddings]].")
        w("wiki/concepts/vector-database.md", "Vector Database", "concept",
          "Stores [[Embeddings]] for nearest-neighbour search.")
        w("wiki/concepts/embeddings.md", "Embeddings", "concept", "Dense vectors.")
        w("wiki/concepts/chunking.md", "Chunking", "concept", "Splits documents.")
        w("wiki/concepts/reranking.md", "Reranking", "concept", "Re-scores passages.")
    elif name.startswith("03"):
        w("wiki/concepts/attention.md", "Attention", "concept", "Weighs tokens.")
        w("wiki/concepts/tokenization.md", "Tokenization", "concept", "Splits text.")
        w("wiki/concepts/inference.md", "Inference", "concept", "Forward pass.")
    elif name.startswith("04"):
        # WRONG on purpose: a duplicate of the case-01 concept.
        w("wiki/concepts/embedding-vectors.md", "Embedding Vectors", "concept",
          "Same idea as vector embeddings, duplicated.")
    elif name.startswith("05"):
        w("wiki/entities/ashish-vaswani.md", "Ashish Vaswani", "entity", "Researcher.")
        w("wiki/entities/noam-shazeer.md", "Noam Shazeer", "entity", "Researcher.")

    return IngestionResult(summary=f"ingested {name}", new_pages=new_pages)


@pytest.fixture
def cfg(tmp_path: Path) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=tmp_path / "placeholder", model="fake:test")


def test_run_evals_produces_report(cfg: WorkspaceConfig) -> None:
    report = evals_service.run_evals(cfg, dataset_dir=DATASET, runner=_fake_runner)
    assert report.model == "fake:test"
    by_name = {c.name: c for c in report.cases}
    # All five dataset cases evaluated.
    assert {"01-short-concept", "02-rich-multi", "03-long", "04-duplicate",
            "05-entities"} <= set(by_name)
    # The rich case produced its concepts and the must_link holds.
    rich = by_name["02-rich-multi"]
    assert rich.pages_created >= 5
    assert rich.must_link_ok
    assert rich.score >= 60


def test_case_04_detects_duplicate(cfg: WorkspaceConfig) -> None:
    report = evals_service.run_evals(cfg, dataset_dir=DATASET, runner=_fake_runner)
    dup = next(c for c in report.cases if c.name == "04-duplicate")
    assert dup.duplicate_created is True
    assert dup.score <= 25  # hard-capped for a created duplicate


def test_brain_is_removed_by_default(cfg: WorkspaceConfig, tmp_path: Path) -> None:
    import llmwiki.core.paths as paths_mod

    saved = paths_mod.WIKI_HOME
    evals_service.run_evals(cfg, dataset_dir=DATASET, runner=_fake_runner)
    # WIKI_HOME restored after the run.
    assert paths_mod.WIKI_HOME == saved


def test_keep_brain_leaves_workdir(cfg: WorkspaceConfig) -> None:
    report = evals_service.run_evals(
        cfg, dataset_dir=DATASET, runner=_fake_runner, keep_brain=True
    )
    assert report.score > 0


def test_write_result_json(cfg: WorkspaceConfig, tmp_path: Path) -> None:
    report = evals_service.run_evals(cfg, dataset_dir=DATASET, runner=_fake_runner)
    out = evals_service.write_result_json(report, tmp_path)
    assert out.exists()
    assert out.parent == tmp_path / "evals" / "results"
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["model"] == "fake:test"


def test_empty_dataset_raises(cfg: WorkspaceConfig, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No eval cases"):
        evals_service.run_evals(cfg, dataset_dir=empty, runner=_fake_runner)
