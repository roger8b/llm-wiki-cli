"""Configuração do workspace, lida de ``.llmwiki/config.yaml``.

Em Fase 0 só carregamos campos básicos. ``model`` é usado a partir da Fase 1
(formato DeepAgents ``provider:model``).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from .paths import BrainPaths


class WorkspaceConfig(BaseModel):
    brain_root: Path
    model: str = "ollama:llama3.1"
    fts_limit: int = 20

    @property
    def paths(self) -> BrainPaths:
        return BrainPaths(root=self.brain_root)


def _config_file(paths: BrainPaths) -> Path:
    return paths.dot / "config.yaml"


def load_config(paths: BrainPaths) -> WorkspaceConfig:
    """Carrega config do brain; usa defaults para campos ausentes."""
    cfg_path = _config_file(paths)
    data: dict[str, object] = {}
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data["brain_root"] = paths.root
    return WorkspaceConfig.model_validate(data)


def write_default_config(paths: BrainPaths) -> None:
    """Escreve um config.yaml inicial dentro de ``.llmwiki/``."""
    cfg_path = _config_file(paths)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    defaults = {"model": "ollama:llama3.1", "fts_limit": 20}
    cfg_path.write_text(
        yaml.safe_dump(defaults, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
