"""Resolução de contexto (brain + config) para a API.

A registry (em ~/.wiki/config.yaml) é a fonte da verdade. ``WIKI_BRAIN``
(desktop/CLI/testes) é sincronizado para a registry, então a UI sempre enxerga
o brain em uso. Sem brain registrado → BrainNotFoundError (onboarding).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ...core.brains import (
    BrainNotFoundError,
    get_active_brain,
    is_brain_dir,
    list_brains,
    register_or_get,
    set_active_brain,
)
from ...core.config import WorkspaceConfig, load_config
from ...core.paths import BrainPaths, load_brain_for_info


def get_paths() -> BrainPaths:
    """Resolve the active brain's paths — registry is the source of truth.

    1. ``WIKI_BRAIN`` env: synced into the registry (registered + activated if
       absent) so env-based access and the UI never diverge.
    2. registry ``activeBrainId`` (if its path still exists).
    3. self-heal: if the active brain's path vanished (e.g. an ephemeral /tmp
       brain after reboot), fall back to the first registered brain whose path
       still exists and make it active — instead of breaking the whole app.
    """
    env = os.environ.get("WIKI_BRAIN")
    if env:
        root = Path(env).resolve()
        if is_brain_dir(root):
            brain = register_or_get(root, activate=True)
            return load_brain_for_info(brain)

    active = get_active_brain()
    if active and is_brain_dir(Path(active.path)):
        return load_brain_for_info(active)

    # self-heal: active is missing/dead → pick the first valid registered brain
    for brain in list_brains():
        if is_brain_dir(Path(brain.path)):
            if active is None or active.id != brain.id:
                set_active_brain(brain.id)
            return load_brain_for_info(brain)

    raise BrainNotFoundError(
        "No usable brain. Register one (POST /api/brains) or create one "
        "(POST /api/brains/create)."
    )


def get_config() -> WorkspaceConfig:
    return load_config(get_paths())


def open_conn(paths: BrainPaths) -> sqlite3.Connection:
    from ...db.connection import get_connection

    return get_connection(paths.db_path)