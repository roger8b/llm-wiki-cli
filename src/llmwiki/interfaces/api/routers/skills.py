"""Agent-skills endpoints — same `skills_service` the CLI uses (CLI/UI parity)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()


@router.get("")
def status(scope: str = "global", agent: str = "claude") -> dict[str, Any]:
    """Available (shipped) skills + installed state for the given scope/agent."""
    from ....services import skills_service

    try:
        listed = skills_service.list_installed(scope=scope, agent=agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"available": skills_service.available(), **listed}


@router.get("/doctor")
def doctor(scope: str = "global", agent: str = "claude") -> dict[str, Any]:
    """Integrity report for installed skills."""
    from ....services import skills_service

    try:
        return skills_service.doctor(scope=scope, agent=agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/install")
def install(
    scope: str = Body("global", embed=True),
    agent: str = Body("claude", embed=True),
    force: bool = Body(False, embed=True),
) -> dict[str, Any]:
    """Install the shipped skills into the agent's skills directory."""
    from ....services import skills_service

    try:
        return skills_service.install(scope=scope, agent=agent, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/update")
def update(
    scope: str = Body("global", embed=True),
    agent: str = Body("claude", embed=True),
) -> dict[str, Any]:
    """Reinstall the shipped skills (refresh to this version)."""
    from ....services import skills_service

    try:
        return skills_service.update(scope=scope, agent=agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/remove")
def remove(
    name: str | None = Body(None, embed=True),
    scope: str = Body("global", embed=True),
    agent: str = Body("claude", embed=True),
) -> dict[str, Any]:
    """Remove one skill (or all when name is omitted)."""
    from ....services import skills_service

    try:
        return skills_service.remove(name, scope=scope, agent=agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
