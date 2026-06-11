"""Tests for semantic-ish duplicate detection (issue #167)."""

from __future__ import annotations

from llmwiki.core.dedup import _levenshtein, find_similar_pages
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import index_service


def _add_page(brain: BrainPaths, rel: str, title: str, body: str) -> None:
    page = brain.wiki / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        f"---\ntitle: {title}\ntype: concept\n---\n# {title}\n{body}\n", encoding="utf-8"
    )


def _reindex(brain: BrainPaths) -> None:
    conn = get_connection(brain.db_path)
    try:
        index_service.reindex(brain, conn)
    finally:
        conn.close()


def test_levenshtein() -> None:
    assert _levenshtein("rag", "rag") == 0
    assert _levenshtein("rag", "rog") == 1
    assert _levenshtein("kitten", "sitting") == 3


def test_exact_slug_match(brain: BrainPaths) -> None:
    _add_page(brain, "concepts/rag.md", "RAG", "retrieval augmented generation")
    _reindex(brain)
    conn = get_connection(brain.db_path)
    try:
        hits = find_similar_pages("RAG", conn)
    finally:
        conn.close()
    assert any(p == "wiki/concepts/rag.md" for p, _, _ in hits)


def test_close_slug_match(brain: BrainPaths) -> None:
    _add_page(brain, "concepts/kubernetes.md", "Kubernetes", "container orchestration")
    _reindex(brain)
    conn = get_connection(brain.db_path)
    try:
        hits = find_similar_pages("Kubernete", conn)  # edit distance 1
    finally:
        conn.close()
    assert any("kubernetes" in p for p, _, _ in hits)


def test_text_match_acronym(brain: BrainPaths) -> None:
    # Proposing the spelled-out title should find the existing acronym page.
    _add_page(
        brain, "concepts/rag.md", "RAG",
        "Retrieval Augmented Generation grounds answers in a knowledge base.",
    )
    _reindex(brain)
    conn = get_connection(brain.db_path)
    try:
        hits = find_similar_pages("Retrieval Augmented Generation", conn)
    finally:
        conn.close()
    assert any(p == "wiki/concepts/rag.md" for p, _, _ in hits)


def test_word_order_and_plural_match(brain: BrainPaths) -> None:
    # "Embedding Vectors" must be flagged as a dup of "Vector Embeddings"
    # (same tokens, different order + plural) — the baseline's case 04.
    _add_page(brain, "concepts/vector-embeddings.md", "Vector Embeddings", "dense vectors")
    _reindex(brain)
    conn = get_connection(brain.db_path)
    try:
        hits = find_similar_pages("Embedding Vectors", conn)
    finally:
        conn.close()
    assert any(p == "wiki/concepts/vector-embeddings.md" for p, _, _ in hits)


def test_shared_word_is_not_a_false_positive(brain: BrainPaths) -> None:
    # "Vector Database" shares only one token with "Vector Embeddings" → not a dup.
    _add_page(brain, "concepts/vector-embeddings.md", "Vector Embeddings", "dense vectors")
    _reindex(brain)
    conn = get_connection(brain.db_path)
    try:
        hits = find_similar_pages("Vector Database", conn)
    finally:
        conn.close()
    assert all(p != "wiki/concepts/vector-embeddings.md" for p, _, _ in hits)


def test_no_match(brain: BrainPaths) -> None:
    _add_page(brain, "concepts/rag.md", "RAG", "retrieval augmented generation")
    _reindex(brain)
    conn = get_connection(brain.db_path)
    try:
        hits = find_similar_pages("Photosynthesis in Plants", conn)
    finally:
        conn.close()
    assert hits == []
