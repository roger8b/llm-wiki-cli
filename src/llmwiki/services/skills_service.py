"""Installable agent skills shipped with the CLI (local-first).

Skills are ``SKILL.md`` artifacts (+ optional flat support files) packaged under
``llmwiki/skills/<name>/``. They teach an agent to operate the brain through the
real CLI (the behavioral contract). This service installs them into an agent's
skills directory and tracks state in a manifest, so the same logic backs both the
CLI (`wiki skills ...`) and the API (`/api/skills/*`).
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

from .. import __version__
from ..core.misc import now_iso

_SKILLS_PKG = "llmwiki.skills"
MANIFEST_NAME = ".llmwiki-skills.json"

# Agent adapters: map an agent name to its skills directory under a base root.
# v1 ships only "claude"; the seam lets new agents be added without touching the
# install/list/doctor logic (#71).
_ADAPTERS: dict[str, str] = {
    "claude": ".claude/skills",
}
DEFAULT_AGENT = "claude"


# ─────────────────────────────────────────── discovery (packaged skills)

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
    """Flat list of file names inside a packaged skill dir."""
    return sorted(f.name for f in _skills_root().joinpath(name).iterdir() if f.is_file())


def _packaged_text(name: str, filename: str) -> str:
    return _skills_root().joinpath(name).joinpath(filename).read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────── target resolution (adapters)

def resolve_skills_dir(
    *, scope: str = "local", agent: str = DEFAULT_AGENT, root: Path | None = None
) -> Path:
    """Resolve the agent's skills directory.

    scope: ``local`` -> under ``root`` (default cwd); ``global`` -> under ~.
    """
    if agent not in _ADAPTERS:
        raise ValueError(f"Unknown agent adapter: {agent} (known: {', '.join(_ADAPTERS)})")
    if scope == "local":
        base = root or Path.cwd()
    elif scope == "global":
        base = Path.home()
    else:
        raise ValueError(f"Unknown scope: {scope} (use 'local' or 'global')")
    return (base / _ADAPTERS[agent]).resolve()


def _manifest_path(skills_dir: Path) -> Path:
    return skills_dir / MANIFEST_NAME


def _read_manifest(skills_dir: Path) -> dict[str, Any]:
    path = _manifest_path(skills_dir)
    if not path.is_file():
        return {"version": __version__, "skills": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": __version__, "skills": {}}


def _write_manifest(skills_dir: Path, manifest: dict[str, Any]) -> None:
    skills_dir.mkdir(parents=True, exist_ok=True)
    _manifest_path(skills_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────── operations

def install(
    *,
    scope: str = "local",
    agent: str = DEFAULT_AGENT,
    root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Install all packaged skills into the agent's skills dir; write the manifest.

    Idempotent: re-running overwrites the shipped files and refreshes the manifest.
    """
    skills_dir = resolve_skills_dir(scope=scope, agent=agent, root=root)
    manifest = _read_manifest(skills_dir)
    installed: list[str] = []

    for name in available():
        dest = skills_dir / name
        existing = manifest["skills"].get(name)
        if existing and not force:
            # already recorded; reinstall anyway to stay in sync (idempotent)
            pass
        dest.mkdir(parents=True, exist_ok=True)
        skill_md = _packaged_text(name, "SKILL.md")
        for filename in _skill_files(name):
            (dest / filename).write_text(
                _packaged_text(name, filename), encoding="utf-8"
            )
        manifest["skills"][name] = {
            "name": name,
            "version": __version__,
            "scope": scope,
            "agent": agent,
            "target": str(dest),
            "checksum": _sha256(skill_md),
            "installed_at": now_iso(),
        }
        installed.append(name)

    manifest["version"] = __version__
    _write_manifest(skills_dir, manifest)
    return {"target": str(skills_dir), "scope": scope, "agent": agent, "installed": installed}


def list_installed(
    *, scope: str = "local", agent: str = DEFAULT_AGENT, root: Path | None = None
) -> dict[str, Any]:
    """List installed skills from the manifest, annotated with on-disk status."""
    skills_dir = resolve_skills_dir(scope=scope, agent=agent, root=root)
    manifest = _read_manifest(skills_dir)
    skills = []
    for entry in sorted(manifest["skills"].values(), key=lambda e: e["name"]):
        present = (Path(entry["target"]) / "SKILL.md").is_file()
        skills.append({**entry, "present": present})
    return {"target": str(skills_dir), "skills": skills}


def doctor(
    *, scope: str = "local", agent: str = DEFAULT_AGENT, root: Path | None = None
) -> dict[str, Any]:
    """Integrity check: manifest vs disk vs shipped (missing / changed / outdated)."""
    skills_dir = resolve_skills_dir(scope=scope, agent=agent, root=root)
    manifest = _read_manifest(skills_dir)
    shipped = set(available())
    issues: list[dict[str, str]] = []

    for name, entry in sorted(manifest["skills"].items()):
        md = Path(entry["target"]) / "SKILL.md"
        if not md.is_file():
            issues.append({"skill": name, "issue": "missing", "detail": "SKILL.md not on disk"})
            continue
        on_disk = _sha256(md.read_text(encoding="utf-8"))
        if name in shipped and on_disk != _sha256(_packaged_text(name, "SKILL.md")):
            issues.append({"skill": name, "issue": "modified", "detail": "differs from shipped"})
        if entry.get("version") != __version__:
            issues.append(
                {
                    "skill": name,
                    "issue": "outdated",
                    "detail": f"{entry.get('version')} != {__version__}",
                }
            )

    not_installed = sorted(shipped - set(manifest["skills"]))
    return {
        "target": str(skills_dir),
        "ok": not issues,
        "issues": issues,
        "available_not_installed": not_installed,
    }


def update(
    *, scope: str = "local", agent: str = DEFAULT_AGENT, root: Path | None = None
) -> dict[str, Any]:
    """Reinstall the shipped skills (refresh content + manifest to the CLI version)."""
    return install(scope=scope, agent=agent, root=root, force=True)


def remove(
    name: str | None = None,
    *,
    scope: str = "local",
    agent: str = DEFAULT_AGENT,
    root: Path | None = None,
) -> dict[str, Any]:
    """Remove one skill (by name) or all installed skills; update the manifest.

    Idempotent: removing something not installed is a no-op.
    """
    import shutil

    skills_dir = resolve_skills_dir(scope=scope, agent=agent, root=root)
    manifest = _read_manifest(skills_dir)
    targets = [name] if name else list(manifest["skills"].keys())
    removed: list[str] = []

    for skill in targets:
        entry = manifest["skills"].pop(skill, None)
        if entry is None:
            continue
        dest = Path(entry["target"])
        if dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        removed.append(skill)

    _write_manifest(skills_dir, manifest)
    return {"target": str(skills_dir), "removed": removed}
