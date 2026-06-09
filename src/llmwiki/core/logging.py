"""Logging bootstrap.

The library code only ever calls ``logging.getLogger("llmwiki.…")`` and never
configures handlers (that is the application's job). Entry points — the CLI, the
API server, and the background worker — call :func:`configure_logging` once at
startup so the agent telemetry and audit warnings actually reach the user.

Controlled by two environment variables:

- ``LLMWIKI_LOG_LEVEL`` — ``DEBUG`` | ``INFO`` | ``WARNING`` (default) |
  ``ERROR``. ``INFO`` surfaces the per-run telemetry line
  (model / tokens / latency / tool calls / fallback).
- ``LLMWIKI_LOG_FILE`` — optional path; when set, logs are also appended there.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(*, force: bool = False) -> None:
    """Attach handlers to the ``llmwiki`` logger from env vars. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level_name = os.environ.get("LLMWIKI_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)

    root = logging.getLogger("llmwiki")
    root.setLevel(level)
    root.handlers.clear()
    # Keep propagate=True: the root logger has no handler by default, so there is
    # no duplication, and pytest's caplog (which captures via propagation) keeps
    # working for ``llmwiki.*`` loggers.

    formatter = logging.Formatter(_FORMAT)

    stream = logging.StreamHandler()  # stderr
    stream.setFormatter(formatter)
    root.addHandler(stream)

    log_file = os.environ.get("LLMWIKI_LOG_FILE")
    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _CONFIGURED = True
