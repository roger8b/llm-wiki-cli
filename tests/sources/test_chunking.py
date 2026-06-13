"""Unit tests for the deterministic chunker (#162)."""

from __future__ import annotations

from llmwiki.sources.chunking import chunk_text


def test_short_text_single_chunk() -> None:
    text = "one paragraph\n\nanother one\n"
    assert chunk_text(text, size=1000, overlap=100) == [text]


def test_empty_text_no_chunks() -> None:
    assert chunk_text("", size=100, overlap=10) == []


def test_splits_on_paragraph_boundaries() -> None:
    paras = [f"Paragraph number {i} " + "x" * 80 for i in range(20)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, size=300, overlap=0)
    assert len(chunks) > 1
    # Every chunk stays at/under size (no oversize, no mid-paragraph cut here).
    for c in chunks:
        assert len(c) <= 300


def test_overlap_carries_context() -> None:
    paras = [f"P{i} " + "y" * 60 for i in range(10)]
    text = "\n\n".join(paras)
    no_overlap = chunk_text(text, size=200, overlap=0)
    with_overlap = chunk_text(text, size=200, overlap=80)
    # Overlap duplicates tail content, so it needs at least as many chunks.
    assert len(with_overlap) >= len(no_overlap)
    # The start of chunk 2 should echo content from the end of chunk 1.
    assert any(
        with_overlap[0].rstrip()[-20:] in with_overlap[1]
        for _ in [0]
    ) or with_overlap[1] != no_overlap[1]


def test_code_fence_never_split() -> None:
    fence = "```python\n" + "\n".join(f"line_{i} = {i}" for i in range(60)) + "\n```"
    text = f"intro paragraph\n\n{fence}\n\noutro paragraph"
    chunks = chunk_text(text, size=200, overlap=0)
    # The full fence survives intact inside exactly one chunk.
    assert any(fence in c for c in chunks)
    # No chunk contains an unbalanced number of fence markers.
    for c in chunks:
        assert c.count("```") % 2 == 0


def test_reassembles_without_overlap() -> None:
    paras = [f"block {i}\n\n" for i in range(30)]
    text = "".join(paras)
    chunks = chunk_text(text, size=120, overlap=0)
    assert "".join(chunks) == text


def test_huge_single_paragraph_hard_split() -> None:
    text = "word " * 2000  # ~10k chars, no paragraph breaks
    chunks = chunk_text(text, size=500, overlap=0)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 500


def test_overlap_clamped_below_size() -> None:
    # overlap >= size would stall; it is clamped to size//2 internally.
    text = "\n\n".join("p" + "z" * 50 for _ in range(20))
    chunks = chunk_text(text, size=100, overlap=999)
    assert len(chunks) > 1
