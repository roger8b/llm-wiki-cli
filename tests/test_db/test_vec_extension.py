"""load_vec_extension degrades safely vs loads sqlite-vec (#319).

The shipped sidecar must bundle a ``sqlite3`` whose build exposes
``enable_load_extension``; when it doesn't, the loader must return False
without crashing so callers degrade to FTS-only (regression-safe).
"""

from __future__ import annotations

import sqlite3

import pytest

from llmwiki.db.connection import load_vec_extension


class _NoExtConn:
    """Stub mimicking a sqlite3 build without loadable-extension support:
    accessing ``enable_load_extension`` raises AttributeError."""


def test_load_vec_extension_false_without_support() -> None:
    # No enable_load_extension attribute → AttributeError caught → False, no crash.
    assert load_vec_extension(_NoExtConn()) is False


def test_load_vec_extension_true_when_supported() -> None:
    conn = sqlite3.connect(":memory:")
    if not hasattr(conn, "enable_load_extension"):
        pytest.skip("sqlite3 built without loadable-extension support")
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        pytest.skip("[semantic] extra (sqlite-vec) not installed")
    assert load_vec_extension(conn) is True
