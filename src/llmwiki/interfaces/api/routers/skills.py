"""Agent-skills endpoints — same `skills_service` the CLI uses (CLI/UI parity)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class InstallReq(BaseModel):
    agents: list[str] | None = None
    agent: str | None = None
    scope: str = "local"
    method: str = "symlink"
    force: bool = False


class RemoveReq(BaseModel):
    name: str | None = None
    agent: str | None = None
    scope: str | None = None


@router.get("")
def status() -> dict[str, Any]:
    """Shipped skills + all recorded installs (across agents/scopes)."""
    from ....services import skills_service

    return skills_service.list_installed()


@router.get("/agents")
def agents() -> dict[str, Any]:
    """All known agents + which are detected on this machine."""
    from ....core import agents as agents_mod

    detected = set(agents_mod.detect_installed_agents())
    return {
        "agents": [
            {"name": name, "display": spec.display, "detected": name in detected}
            for name, spec in agents_mod.AGENTS.items()
        ]
    }


@router.get("/doctor")
def doctor() -> dict[str, Any]:
    from ....services import skills_service

    return skills_service.doctor()


@router.post("/install")
def install(req: InstallReq) -> dict[str, Any]:
    """Install skills for the given agents/scope/method."""
    from ....services import skills_service

    try:
        return skills_service.install(
            agents=req.agents, agent=req.agent, scope=req.scope, method=req.method, force=req.force
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/update")
def update() -> dict[str, Any]:
    from ....services import skills_service

    return skills_service.update()


@router.post("/remove")
def remove(req: RemoveReq) -> dict[str, Any]:
    from ....services import skills_service

    try:
        return skills_service.remove(req.name, agent=req.agent, scope=req.scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
