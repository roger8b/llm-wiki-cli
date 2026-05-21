"""Pequenos utilitários puros: hashing e datas."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime


def sha256(data: str | bytes) -> str:
    """SHA-256 hex de uma string (utf-8) ou bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def today() -> str:
    """Data atual em ISO (YYYY-MM-DD)."""
    return date.today().isoformat()


def now_iso() -> str:
    """Timestamp atual UTC em ISO8601."""
    return datetime.now(UTC).isoformat()
