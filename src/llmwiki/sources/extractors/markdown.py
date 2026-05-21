"""Extrator de Markdown/texto puro: lê o arquivo como utf-8."""

from __future__ import annotations

from pathlib import Path


def extract(path: Path) -> str:
    return path.read_text(encoding="utf-8")
