"""Installable agent skills — central store + symlink/copy install (multi-agent).

Skills ship as ``SKILL.md`` artifacts under ``llmwiki/skills/<name>/``. They are
materialized once into a **central store** (``~/.wiki/skills``) — the single
source of truth on the machine — and then linked into each agent's skills
directory (symlink by default, copy as a fallback), per workspace (``local``) or
per user (``global``). Updating the store propagates to every symlink. A global
manifest records every install so list/doctor/remove are multi-agent aware.
"""

from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from .. import __version__
from ..core import paths as _paths
from ..core.agents import AGENTS, resolve_agent
from ..core.misc import now_iso

_SKILLS_PKG = "llmwiki.skills"


def _store() -> Path:
    """Central skill store (~/.wiki/skills), resolved at call-time so tests that
    redirect WIKI_HOME are honored."""
    return _paths.WIKI_HOME / "skills"


def _manifest_path() -> Path:
    return _store() / ".installs.json"


# ─────────────────────────────────────────── packaged skills + central store

def _skills_root() -> Any:
    return resources.files(_SKILLS_PKG)


def available() -> list[str]:
    """Names of skills shipped with the CLI (dirs containing a SKILL.md)."""
    out: list[str] = []
    for entry in _skills_root().iterdir():
        if entry.is_dir() and entry.joinpath("SKILL.md").is_file():
            out.append(entry.name)
    return sorted(out)


def _skill_files(name: str) -> list[str]:
    return sorted(f.name for f in _skills_root().joinpath(name).iterdir() if f.is_file())


def sync_store() -> Path:
    """Materialize the packaged skills into the central store (~/.wiki/skills)."""
    _store().mkdir(parents=True, exist_ok=True)
    for name in available():
        dest = _store() / name
        dest.mkdir(parents=True, exist_ok=True)
        for filename in _skill_files(name):
            content = _skills_root().joinpath(name).joinpath(filename).read_text(encoding="utf-8")
            (dest / filename).write_text(content, encoding="utf-8")
    return _store()


# ─────────────────────────────────────────── manifest

def _read_manifest() -> dict[str, Any]:
    if not _manifest_path().is_file():
        return {"version": __version__, "installs": {}}
    try:
        raw: Any = json.loads(_manifest_path().read_text(encoding="utf-8"))
        data: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
        data.setdefault("installs", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": __version__, "installs": {}}


def _write_manifest(data: dict[str, Any]) -> None:
    _store().mkdir(parents=True, exist_ok=True)
    data["version"] = __version__
    _manifest_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────── destination resolution

def _resolve_dests(
    agents: list[str], scope: str, root: Path
) -> dict[Path, list[str]]:
    """Map each target skills dir to the agent(s) that share it (dedup)."""
    if scope not in ("local", "global", "both"):
        raise ValueError(f"Unknown scope: {scope} (use local | global | both)")
    scopes = ["local", "global"] if scope == "both" else [scope]
    dests: dict[Path, list[str]] = {}
    for name in agents:
        spec = AGENTS[resolve_agent(name)]
        for sc in scopes:
            d = spec.skills_dir(sc, root).resolve()
            dests.setdefault(d, [])
            if spec.name not in dests[d]:
                dests[d].append(spec.name)
    return dests


def _rm(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _link_one(src: Path, link: Path, method: str, force: bool) -> bool:
    """Symlink (or copy) one skill dir into a destination. Returns True if written."""
    if link.is_symlink() or link.exists():
        if not force:
            return False
        _rm(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    if method == "symlink":
        try:
            os.symlink(src, link, target_is_directory=True)
            return True
        except OSError:
            pass  # fall back to copy (e.g. FS without symlink support)
    shutil.copytree(src, link)
    return True


# ─────────────────────────────────────────── operations

def install(
    *,
    agents: list[str] | None = None,
    agent: str | None = None,
    scope: str = "local",
    method: str = "symlink",
    root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Install skills into the chosen agents' skills dirs from the central store."""
    if method not in ("symlink", "copy"):
        raise ValueError(f"Unknown method: {method} (use symlink | copy)")
    names = list(agents or ([] if agent is None else [agent])) or ["claude"]
    names = [resolve_agent(n) for n in names]

    sync_store()
    root = (root or Path.cwd()).resolve()
    manifest = _read_manifest()
    results: list[dict[str, Any]] = []

    for dest, dest_agents in _resolve_dests(names, scope, root).items():
        written: list[str] = []
        for name in available():
            if _link_one(_store() / name, dest / name, method, force):
                written.append(name)
        manifest["installs"][str(dest)] = {
            "dest": str(dest),
            "agents": dest_agents,
            "scope": scope,
            "method": method,
            "skills": available(),
            "version": __version__,
            "installed_at": now_iso(),
        }
        results.append({"dest": str(dest), "agents": dest_agents, "written": written})

    _write_manifest(manifest)
    return {"store": str(_store()), "method": method, "scope": scope, "results": results}


def _skill_status(dest: Path, name: str) -> dict[str, Any]:
    link = dest / name
    is_link = link.is_symlink()
    present = link.exists()  # follows symlink; False if the target is gone
    return {"name": name, "present": present, "symlink": is_link, "broken": is_link and not present}


def list_installed() -> dict[str, Any]:
    """All recorded installs (across agents/scopes) annotated with on-disk status."""
    manifest = _read_manifest()
    installs = []
    for rec in manifest["installs"].values():
        dest = Path(rec["dest"])
        installs.append(
            {
                **rec,
                "skills_status": [_skill_status(dest, n) for n in rec.get("skills", [])],
            }
        )
    return {"store": str(_store()), "available": available(), "installs": installs}


def doctor() -> dict[str, Any]:
    """Integrity check across all installs: missing / broken symlink / outdated."""
    manifest = _read_manifest()
    issues: list[dict[str, str]] = []
    for rec in manifest["installs"].values():
        dest = Path(rec["dest"])
        for name in rec.get("skills", []):
            link = dest / name
            if link.is_symlink() and not link.exists():
                issues.append({"dest": rec["dest"], "skill": name, "issue": "broken-symlink"})
            elif not link.is_symlink() and not link.exists():
                issues.append({"dest": rec["dest"], "skill": name, "issue": "missing"})
        if rec.get("version") != __version__:
            issues.append({"dest": rec["dest"], "skill": "*", "issue": "outdated"})
    return {"store": str(_store()), "ok": not issues, "issues": issues}


def update() -> dict[str, Any]:
    """Refresh the store and re-link every recorded install (copies get refreshed)."""
    sync_store()
    manifest = _read_manifest()
    refreshed = []
    for rec in list(manifest["installs"].values()):
        dest = Path(rec["dest"])
        for name in rec.get("skills", []):
            _link_one(_store() / name, dest / name, rec.get("method", "symlink"), force=True)
        rec["version"] = __version__
        rec["installed_at"] = now_iso()
        refreshed.append(rec["dest"])
    _write_manifest(manifest)
    return {"store": str(_store()), "refreshed": refreshed}


def remove(
    name: str | None = None,
    *,
    agent: str | None = None,
    scope: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Remove installed skill links. Never touches the central store.

    name: a specific skill (omit for all). agent/scope: limit which installs.
    """
    manifest = _read_manifest()
    root = (root or Path.cwd()).resolve()
    keep_dests: set[str] | None = None
    if agent or scope:
        agents = [resolve_agent(agent)] if agent else list(AGENTS)
        keep_dests = {str(d) for d in _resolve_dests(agents, scope or "both", root)}

    removed: list[str] = []
    for dest_str, rec in list(manifest["installs"].items()):
        if keep_dests is not None and dest_str not in keep_dests:
            continue
        dest = Path(dest_str)
        skills = [name] if name else list(rec.get("skills", []))
        for skill in skills:
            link = dest / skill
            if link.is_symlink() or link.exists():
                _rm(link)
                removed.append(f"{dest_str}/{skill}")
        if name:
            rec["skills"] = [s for s in rec.get("skills", []) if s != name]
            if not rec["skills"]:
                manifest["installs"].pop(dest_str, None)
        else:
            manifest["installs"].pop(dest_str, None)

    _write_manifest(manifest)
    return {"store": str(_store()), "removed": removed}
