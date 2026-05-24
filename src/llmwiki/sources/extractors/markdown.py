"""Markdown/plain text extractor: reads the file as utf-8."""

from __future__ import annotations

from pathlib import Path


def extract(path: Path) -> str:
    return path.read_text(encoding="utf-8")
