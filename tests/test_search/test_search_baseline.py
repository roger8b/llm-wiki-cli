"""Tests for the retrieval eval harness (#349, epic #348).

Covers the golden-set parser, the recall@k / MRR math and an end-to-end smoke
of ``scripts/search_baseline.py`` against a tiny fixture brain — no LLM, no
embeddings (semantic layer off ⇒ keyword == hybrid).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_harness():
    path = Path(__file__).resolve().parents[2] / "scripts" / "search_baseline.py"
    spec = importlib.util.spec_from_file_location("search_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses (py3.14) resolve the defining module via sys.modules.
    sys.modules["search_baseline"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- golden set parser ----------------------------------------------------


def test_load_golden_parses_search_and_ask(tmp_path):
    hb = _load_harness()
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        """
search:
  - id: exact-rag
    class: exact
    query: RAG
    expected: [wiki/concepts/rag.md]
  - id: neg-01
    class: negative
    query: culinária basca medieval
    expected: []
ask:
  - id: ask-01
    question: O que é RAG?
""",
        encoding="utf-8",
    )
    cases, ask_cases = hb.load_golden(golden)
    assert [c.id for c in cases] == ["exact-rag", "neg-01"]
    assert cases[0].cls == "exact"
    assert cases[0].expected == ["wiki/concepts/rag.md"]
    assert cases[1].cls == "negative" and cases[1].expected == []
    assert ask_cases[0].question == "O que é RAG?"


def test_load_golden_rejects_unknown_class(tmp_path):
    hb = _load_harness()
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        "search:\n  - id: x\n    class: fuzzy\n    query: q\n    expected: [a.md]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="class"):
        hb.load_golden(golden)


def test_load_golden_rejects_inconsistent_expected(tmp_path):
    hb = _load_harness()
    golden = tmp_path / "golden.yaml"
    # negative with expected pages, and non-negative without any — both invalid.
    golden.write_text(
        "search:\n  - id: neg\n    class: negative\n    query: q\n    expected: [a.md]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="negative"):
        hb.load_golden(golden)
    golden.write_text(
        "search:\n  - id: pos\n    class: exact\n    query: q\n    expected: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected"):
        hb.load_golden(golden)


# --- metrics ---------------------------------------------------------------


def test_recall_at_and_mrr_math():
    hb = _load_harness()
    expected = ["a.md", "b.md"]
    ranked = ["x.md", "a.md", "y.md", "z.md", "w.md", "b.md"]
    assert hb.recall_at(expected, ranked, 5) == pytest.approx(0.5)
    assert hb.recall_at(expected, ranked, 10) == pytest.approx(1.0)
    # first relevant at rank 2 -> 1/2
    assert hb.mrr(expected, ranked) == pytest.approx(0.5)
    # no relevant found -> 0
    assert hb.mrr(expected, ["x.md"]) == 0.0
    # empty ranking -> 0, not a crash
    assert hb.recall_at(expected, [], 5) == 0.0


def test_percentiles_small_n():
    hb = _load_harness()
    assert hb.p50([10.0, 20.0]) == pytest.approx(15.0)
    assert hb.p95([10.0, 20.0]) == pytest.approx(20.0)


# --- end-to-end smoke (no LLM, no embeddings) -------------------------------


@pytest.fixture
def fixture_brain(tmp_path, monkeypatch):
    from llmwiki.core import paths as paths_module

    monkeypatch.setattr(paths_module, "WIKI_HOME", tmp_path / ".wiki")
    from llmwiki.core.config import load_config
    from llmwiki.db.connection import get_connection
    from llmwiki.services import index_service, scaffold_service

    paths = scaffold_service.init_brain(tmp_path / "brain", git=False)
    pages = {
        "wiki/concepts/rag.md": (
            "---\ntitle: RAG\ntype: concept\ntags: [rag]\nsources: []\n"
            "updated_at: 2026-01-01\nconfidence: high\n---\n# RAG\n\n"
            "Retrieval-Augmented Generation combina retriever e gerador.\n"
        ),
        "wiki/concepts/vector-store.md": (
            "---\ntitle: Vector Store\ntype: concept\ntags: [search]\nsources: []\n"
            "updated_at: 2026-01-01\nconfidence: high\n---\n# Vector Store\n\n"
            "Armazena embeddings para busca semântica. Ver [[RAG]].\n"
        ),
        "wiki/decisions/use-sqlite.md": (
            "---\ntitle: Use SQLite\ntype: decision\ntags: [db]\nsources: []\n"
            "updated_at: 2026-01-01\nconfidence: high\n---\n# Use SQLite\n\n"
            "Decisão de usar SQLite com FTS5 para o índice local.\n"
        ),
    }
    for rel, content in pages.items():
        target = paths.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    cfg = load_config(paths)
    conn = get_connection(paths.db_path)
    index_service.reindex(paths, conn, cfg)
    yield paths, conn, cfg
    conn.close()


def test_search_eval_smoke(fixture_brain, tmp_path):
    hb = _load_harness()
    paths, conn, cfg = fixture_brain
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        """
search:
  - id: exact-rag
    class: exact
    query: RAG
    expected: [wiki/concepts/rag.md]
  - id: neg-01
    class: negative
    query: zebra quantum banana
    expected: []
""",
        encoding="utf-8",
    )
    cases, _ = hb.load_golden(golden)
    report = hb.run_search_eval(conn, cfg, cases, limit=10)
    # semantic layer off -> semantic mode reports unavailable and 0 cases ranked
    assert report["semantic"]["available"] is False
    for mode in ("keyword", "hybrid"):
        stats = report[mode]
        assert stats["available"] is True
        assert stats["recall_at_5"] == pytest.approx(1.0)
        assert stats["mrr"] == pytest.approx(1.0)
        # the negative query truly has no match in this tiny brain
        assert stats["negative_hit_rate"] == pytest.approx(0.0)
        assert stats["latency_ms_p50"] >= 0.0


def test_render_report_mentions_embeddings_health(fixture_brain, tmp_path):
    hb = _load_harness()
    paths, conn, cfg = fixture_brain
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        "search:\n  - id: e\n    class: exact\n    query: RAG\n"
        "    expected: [wiki/concepts/rag.md]\n",
        encoding="utf-8",
    )
    cases, _ = hb.load_golden(golden)
    report = hb.run_search_eval(conn, cfg, cases, limit=10)
    md = hb.render(
        search_report=report,
        ask_report=None,
        meta=hb.collect_meta(conn, cfg, pages_in_brain=3),
    )
    assert "recall@5" in md
    assert "page_embeddings" in md  # embeddings health is part of the doc (#303)
    assert "keyword" in md and "hybrid" in md
