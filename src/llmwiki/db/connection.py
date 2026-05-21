"""Abertura e inicialização da conexão SQLite."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def _load_schema() -> str:
    return resources.files("llmwiki.db").joinpath("schema.sql").read_text(encoding="utf-8")


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Abre a conexão, aplica o schema (idempotente) e ativa foreign keys.

    ``pages_fts`` (FTS5) é exigida; se o SQLite local não tiver FTS5, o erro
    é propagado de forma explícita.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(_load_schema())
    except sqlite3.OperationalError as exc:
        if "fts5" in str(exc).lower():
            raise RuntimeError(
                "Seu SQLite não tem suporte a FTS5, exigido pela busca. "
                "Instale um Python com SQLite+FTS5."
            ) from exc
        raise
    conn.commit()
    return conn
