"""Geração de unified diff (puro, sem LLM)."""

from __future__ import annotations

import difflib


def make_diff(old: str, new: str, path: str) -> str:
    """Unified diff entre ``old`` e ``new`` rotulado com ``path``.

    Para criação de arquivo, passe ``old=""``. Retorna string vazia se não houver
    diferença.
    """
    if old == new:
        return ""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    # Garante quebra de linha final para um diff limpo.
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)
