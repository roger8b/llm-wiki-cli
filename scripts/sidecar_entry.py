"""PyInstaller entry point for the desktop sidecar.

Wraps the Typer CLI so the compiled binary behaves exactly like the `wiki`
command (the Tauri shell invokes it as `wiki-backend serve --port ... --brain ...`).
"""

from __future__ import annotations

import multiprocessing

from llmwiki.interfaces.cli.main import app

if __name__ == "__main__":
    # uvicorn/anyio may spawn workers; required for frozen apps.
    multiprocessing.freeze_support()
    app()
