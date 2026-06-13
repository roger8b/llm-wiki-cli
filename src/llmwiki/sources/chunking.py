"""Deterministic text chunker for long-source multi-pass ingestion (#162).

No LLM, no embeddings. Splits text on paragraph/heading boundaries, keeps each
chunk under ``size`` characters, and carries ``overlap`` characters of context
into the next chunk so a concept split across a boundary is still seen whole.

Hard guarantee: a fenced code block (``` ... ``` or ~~~ ... ~~~) is never cut in
the middle — it travels as one atomic segment even if that makes a chunk exceed
``size``.
"""

from __future__ import annotations

__all__ = ["chunk_text"]


def _is_fence_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _segment(text: str) -> list[str]:
    """Split ``text`` into atomic segments at blank-line (paragraph) boundaries.

    Code fences are kept intact: blank lines inside a fence do not split it.
    Concatenating the returned segments reproduces ``text`` exactly.
    """
    segments: list[str] = []
    buf: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines(keepends=True):
        if _is_fence_line(line):
            marker = line.lstrip()[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue
        buf.append(line)
        if line.strip() == "":
            segments.append("".join(buf))
            buf = []
    if buf:
        segments.append("".join(buf))
    return [s for s in segments if s]


def _has_fence(seg: str) -> bool:
    return "```" in seg or "~~~" in seg


def _hard_split(seg: str, size: int) -> list[str]:
    """Split an oversize fence-free segment, preferring newline/space boundaries."""
    pieces: list[str] = []
    rest = seg
    while len(rest) > size:
        cut = rest.rfind("\n", 0, size)
        if cut <= 0:
            cut = rest.rfind(" ", 0, size)
        if cut <= 0:
            cut = size
        pieces.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        pieces.append(rest)
    return pieces


def _overlap_tail(segs: list[str], overlap: int) -> list[str]:
    """Trailing segments of ``segs`` whose combined length stays within ``overlap``."""
    if overlap <= 0:
        return []
    tail: list[str] = []
    total = 0
    for seg in reversed(segs):
        if tail and total + len(seg) > overlap:
            break
        tail.insert(0, seg)
        total += len(seg)
    return tail


def chunk_text(text: str, *, size: int, overlap: int) -> list[str]:
    """Split ``text`` into overlapping chunks of at most ``size`` characters.

    Short text (``len <= size``) returns a single chunk unchanged. Overlap is
    clamped to half of ``size`` to guarantee forward progress.
    """
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if len(text) <= size:
        return [text] if text else []

    overlap = max(0, min(overlap, size // 2))
    segments = _segment(text)

    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_len
        if cur and "".join(cur).strip():
            chunks.append("".join(cur))
        cur = _overlap_tail(cur, overlap)
        cur_len = sum(len(s) for s in cur)

    for seg in segments:
        pieces = _hard_split(seg, size) if len(seg) > size and not _has_fence(seg) else [seg]
        for piece in pieces:
            if cur and cur_len + len(piece) > size:
                flush()
            cur.append(piece)
            cur_len += len(piece)

    if cur and "".join(cur).strip():
        chunks.append("".join(cur))
    return chunks
