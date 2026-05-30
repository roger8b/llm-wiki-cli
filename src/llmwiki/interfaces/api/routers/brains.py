"""Brain registry management endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body, HTTPException

from ..deps import get_paths

if TYPE_CHECKING:
    from ....core.brains import BrainInfo

router = APIRouter()


def _ctx() -> Any:
    try:
        return get_paths()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _brains_payload() -> list[dict[str, Any]]:
    """Build the brain list payload from the registry."""
    from pathlib import Path

    from ....core.brains import get_brain_db_path, is_brain_dir, list_brains

    brains = list_brains()
    out: list[dict[str, Any]] = []
    for b in brains:
        db_path = get_brain_db_path(b.id)
        valid = is_brain_dir(Path(b.path))
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "path": b.path,
                "icon": b.icon,
                "db_size": db_path.stat().st_size if db_path.exists() else 0,
                "createdAt": b.createdAt,
                "valid": valid,
            }
        )
    return out


@router.get("")
def list_brains_endpoint() -> list[dict[str, Any]]:
    """List all registered brains from the brain registry."""
    return _brains_payload()


@router.post("")
def create_brain(
    name: str = Body(...),
    path: str = Body(...),
    icon: str = Body("brain"),
    activate: bool = Body(False),
) -> dict[str, Any]:
    """Register an EXISTING brain directory (must already contain a marker)."""
    from ....core.brains import BrainNotValidError, add_brain

    try:
        brain = add_brain(name=name, path=path, icon=icon, activate=activate)
    except BrainNotValidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return brain.to_dict()


@router.post("/create")
def create_and_init_brain(
    name: str = Body(...),
    path: str = Body(...),
    icon: str = Body("brain"),
    activate: bool = Body(True),
) -> dict[str, Any]:
    """Create a NEW brain: scaffold the directory tree, then register it."""
    from pathlib import Path

    from ....core import brains as reg
    from ....core.brains import get_brain
    from ....core.errors import WikiError
    from ....services import scaffold_service

    root = Path(path).expanduser().resolve()
    brain: BrainInfo | None
    try:
        if (root / ".llmwiki").exists():
            brain = reg.register_or_get(root, name=name, activate=activate)
        else:
            paths = scaffold_service.init_brain(root, git=False)
            brain = get_brain(paths.brain_id or "")
        if brain is None:
            raise HTTPException(status_code=500, detail="Brain registration failed.")
        updates: dict[str, str] = {}
        if name and brain.name != name:
            updates["name"] = name
        if icon and brain.icon != icon:
            updates["icon"] = icon
        if updates:
            brain = reg.update_brain(brain.id, updates)
        if activate:
            reg.set_active_brain(brain.id)
    except WikiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot create at {root}: {exc}") from exc
    return brain.to_dict()


@router.get("/active")
def get_active_brain_endpoint() -> dict[str, Any] | None:
    """Get the currently active brain."""
    from ....core.brains import get_active_brain

    brain = get_active_brain()
    return brain.to_dict() if brain else None


@router.post("/active")
def set_active_brain_endpoint(body: dict[str, str]) -> dict[str, Any]:
    """Set the active brain by ID or path."""
    from pathlib import Path

    from ....core.brains import add_brain, list_brains, set_active_brain

    if "id" in body:
        brain = set_active_brain(body["id"])
    elif "path" in body:
        path_brain = next(
            (b for b in list_brains() if b.path == body["path"]), None
        )
        if path_brain:
            brain = set_active_brain(path_brain.id)
        else:
            name = Path(body["path"]).name
            brain = add_brain(name=name, path=body["path"], activate=True)
    else:
        raise HTTPException(status_code=400, detail="Provide 'id' or 'path'")
    return brain.to_dict()


@router.get("/{brain_id}")
def get_brain_endpoint(brain_id: str) -> dict[str, Any]:
    """Get a specific brain by ID."""
    from ....core.brains import get_brain

    brain = get_brain(brain_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")
    return brain.to_dict()


@router.patch("/{brain_id}")
def update_brain_endpoint(
    brain_id: str,
    name: str | None = Body(None),
    path: str | None = Body(None),
    icon: str | None = Body(None),
) -> dict[str, Any]:
    """Update a brain's name, path, or icon."""
    from ....core.brains import update_brain

    updates = {}
    if name is not None:
        updates["name"] = name
    if path is not None:
        updates["path"] = path
    if icon is not None:
        updates["icon"] = icon
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    brain = update_brain(brain_id, updates)
    return brain.to_dict()


@router.post("/{brain_id}/activate")
def activate_brain_endpoint(brain_id: str) -> dict[str, Any]:
    """Activate a specific brain by ID."""
    from ....core.brains import set_active_brain

    brain = set_active_brain(brain_id)
    return brain.to_dict()


@router.delete("/{brain_id}")
def delete_brain_endpoint(brain_id: str) -> dict[str, Any]:
    """Delete a brain by ID."""
    from ....core.brains import get_active_brain, list_brains, remove_brain

    brains = list_brains()
    if len(brains) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last brain. Register another one first.",
        )
    brain = next((b for b in brains if b.id == brain_id), None)
    remove_brain(brain_id)
    active = get_active_brain()
    return {
        "deleted": brain_id,
        "deletedName": brain.name if brain else None,
        "newActiveId": active.id if active else None,
    }