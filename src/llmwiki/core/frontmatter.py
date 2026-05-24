"""Parsing and serialization of YAML frontmatter in Markdown files.

Supported format::

    ---
    title: Foo
    tags: [a, b]
    ---
    # markdown body
"""

from __future__ import annotations

from typing import Any

import yaml

from .errors import InvalidFrontmatterError

_FENCE = "---"


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Splits frontmatter (dict) from body (str).

    No frontmatter → ``({}, text)``. Frontmatter present but YAML invalid →
    ``InvalidFrontmatterError``.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != _FENCE:
        return {}, text

    # Look for the closing fence.
    closing = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            closing = i
            break
    if closing is None:
        return {}, text

    raw_yaml = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1 :])
    if body.startswith("\n"):
        body = body[1:]

    try:
        loaded = yaml.safe_load(raw_yaml) if raw_yaml.strip() else {}
    except yaml.YAMLError as exc:  # noqa: F841
        raise InvalidFrontmatterError(f"Invalid YAML frontmatter: {exc}") from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise InvalidFrontmatterError("Frontmatter must be a YAML mapping.")
    return loaded, body


def dump(meta: dict[str, Any], body: str) -> str:
    """Serializes metadata + body back to text with frontmatter."""
    if not meta:
        return body
    yaml_text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"{_FENCE}\n{yaml_text}\n{_FENCE}\n\n{body.lstrip(chr(10))}"
