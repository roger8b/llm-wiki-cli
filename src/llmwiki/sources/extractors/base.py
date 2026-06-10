"""Shared extractor types (issue #163).

Kept in its own module so individual extractors can import ``ExtractedSource``
without a circular import through the package ``__init__``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedSource:
    """The text plus best-effort provenance metadata of a raw source.

    Fields beyond ``text`` are optional — extractors fill what they can.
    """

    text: str
    title: str | None = None
    author: str | None = None
    date: str | None = None  # ISO when possible
    url: str | None = None
