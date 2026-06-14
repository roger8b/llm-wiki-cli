"""Machine-readable output for the CLI (#196).

Read commands accept ``--json``. With the flag set, the command prints a single
JSON object to stdout and nothing else — no Rich tables, no logging, no banners
(logs already go to stderr via :mod:`llmwiki.core.logging`). Without it, the
existing human renderer runs unchanged.

Envelope policy: top-level payloads are always *named objects* (never a bare
array), so fields can be added later without breaking parsers. Compatibility:
fields are only added, never removed or renamed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


def _to_jsonable(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, dict):
        return {k: _to_jsonable(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_to_jsonable(v) for v in data]
    return data


def emit(data: Any, *, as_json: bool, human: Callable[[], None]) -> None:
    """Print ``data`` as JSON when ``as_json`` else run the ``human`` renderer.

    ``data`` may be a pydantic model, a dict, or a list of models/dicts. In JSON
    mode only ``json.dumps`` reaches stdout; the human callback is not invoked.
    """
    if as_json:
        print(json.dumps(_to_jsonable(data), ensure_ascii=False))
    else:
        human()
