"""CLI installation and management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .. import setup as setup_mod

router = APIRouter()


@router.get("")
def cli_status() -> dict[str, Any]:
    """Get CLI installation status."""
    return setup_mod.cli_status()


@router.post("/install")
def cli_install() -> dict[str, Any]:
    """Install the CLI (symlink to ~/.local/bin)."""
    return setup_mod.cli_install()


@router.delete("")
def cli_uninstall() -> dict[str, Any]:
    """Uninstall the CLI."""
    return setup_mod.cli_uninstall()