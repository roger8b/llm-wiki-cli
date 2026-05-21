"""Parse e serialização de frontmatter YAML em arquivos Markdown.

Formato suportado::

    ---
    title: Foo
    tags: [a, b]
    ---
    # corpo markdown
"""

from __future__ import annotations

from typing import Any

import yaml

from .errors import InvalidFrontmatterError

_FENCE = "---"


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Separa frontmatter (dict) do corpo (str).

    Sem frontmatter → ``({}, text)``. Frontmatter presente mas YAML inválido →
    ``InvalidFrontmatterError``.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != _FENCE:
        return {}, text

    # Procura a cerca de fechamento.
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
        raise InvalidFrontmatterError(f"Frontmatter YAML inválido: {exc}") from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise InvalidFrontmatterError("Frontmatter deve ser um mapeamento YAML.")
    return loaded, body


def dump(meta: dict[str, Any], body: str) -> str:
    """Serializa metadados + corpo de volta para texto com frontmatter."""
    if not meta:
        return body
    yaml_text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"{_FENCE}\n{yaml_text}\n{_FENCE}\n\n{body.lstrip(chr(10))}"
