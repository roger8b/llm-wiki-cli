"""Inject/maintain a managed block of wiki-usage rules in a workspace's agent
rule files (``AGENTS.md`` / ``CLAUDE.md``).

The block lives between markers so it can be created, updated, or removed
idempotently without disturbing the rest of the file. The rules content derives
from the skills contract (#72): consume via ask/search, feed via ingest/CR.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

START_MARKER = "<!-- llm-wiki:start -->"
END_MARKER = "<!-- llm-wiki:end -->"

# Agent rule files written by `wiki init`, in the workspace root.
RULE_FILES = ("AGENTS.md", "CLAUDE.md")


def render_block(brain_name: str) -> str:
    """Render the managed rules block (wrapped in markers) for a given brain."""
    template = (
        resources.files("llmwiki")
        .joinpath("templates", "workspace_rules.md")
        .read_text(encoding="utf-8")
        .replace("{{brain}}", brain_name)
        .strip()
    )
    return f"{START_MARKER}\n{template}\n{END_MARKER}\n"


def _strip_block(text: str) -> str:
    """Remove an existing managed block (and surrounding blank lines) from text."""
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return text
    end += len(END_MARKER)
    before = text[:start].rstrip("\n")
    after = text[end:].lstrip("\n")
    if before and after:
        return f"{before}\n\n{after}"
    return (before or after).rstrip("\n") + ("\n" if (before or after) else "")


def upsert_block(file: Path, block: str) -> str:
    """Create the file with the block, update an existing block, or append it.

    Returns the action taken: ``created`` | ``updated`` | ``appended``.
    """
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(block, encoding="utf-8")
        return "created"

    text = file.read_text(encoding="utf-8")
    if START_MARKER in text and END_MARKER in text:
        stripped = _strip_block(text)
        action = "updated"
    else:
        stripped = text
        action = "appended"

    base = stripped.rstrip("\n")
    new_text = f"{base}\n\n{block}" if base else block
    file.write_text(new_text, encoding="utf-8")
    return action


def remove_block(file: Path) -> bool:
    """Remove the managed block from the file. Returns True if a block was removed."""
    if not file.exists():
        return False
    text = file.read_text(encoding="utf-8")
    if START_MARKER not in text or END_MARKER not in text:
        return False
    file.write_text(_strip_block(text), encoding="utf-8")
    return True
