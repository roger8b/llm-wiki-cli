"""Small pure utilities: hashing and dates."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime


def sha256(data: str | bytes) -> str:
    """SHA-256 hex of a string (utf-8) or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def today() -> str:
    """Current date in ISO format (YYYY-MM-DD)."""
    return date.today().isoformat()


def now_iso() -> str:
    """Current UTC timestamp in ISO8601."""
    return datetime.now(UTC).isoformat()
