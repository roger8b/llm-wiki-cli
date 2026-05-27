"""Registry of supported AI agents and where each expects its skills.

Used by the skills installer to wire skills (symlink/copy) into each agent's
skills directory — per workspace (``local``) or per user (``global``). Inspired
by google-search-cli's agent registry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_HOME = Path.home()
_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or (_HOME / ".config"))
_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (_HOME / ".codex"))
_CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (_HOME / ".claude"))


@dataclass(frozen=True)
class AgentSpec:
    name: str
    display: str
    skills_subdir: str  # workspace-relative skills dir (local scope)
    global_skills_dir: Path  # absolute skills dir (global scope)
    detect_path: Path  # exists() => the agent is installed on this machine

    def skills_dir(self, scope: str, root: Path) -> Path:
        """Resolve this agent's skills dir for a scope (local under root, or global)."""
        if scope == "global":
            return self.global_skills_dir
        return root / self.skills_subdir

    @property
    def installed(self) -> bool:
        return self.detect_path.exists()


AGENTS: dict[str, AgentSpec] = {
    "pi": AgentSpec("pi", "Pi", ".pi/skills", _HOME / ".pi/agent/skills", _HOME / ".pi/agent"),
    "claude-code": AgentSpec(
        "claude-code", "Claude Code", ".claude/skills", _CLAUDE_HOME / "skills", _CLAUDE_HOME
    ),
    "gemini-cli": AgentSpec(
        "gemini-cli", "Gemini CLI", ".agents/skills", _HOME / ".gemini/skills", _HOME / ".gemini"
    ),
    "cursor": AgentSpec(
        "cursor", "Cursor", ".agents/skills", _HOME / ".cursor/skills", _HOME / ".cursor"
    ),
    "codex": AgentSpec(
        "codex", "Codex", ".agents/skills", _CODEX_HOME / "skills", _CODEX_HOME
    ),
    "amp": AgentSpec(
        "amp", "Amp", ".agents/skills", _CONFIG_HOME / "agents/skills", _CONFIG_HOME / "amp"
    ),
}

# Backwards-compatible aliases (v1 used "claude").
_ALIASES = {"claude": "claude-code", "gemini": "gemini-cli"}


def resolve_agent(name: str) -> str:
    """Canonical agent id for a name/alias. Raises ValueError if unknown."""
    key = _ALIASES.get(name, name)
    if key not in AGENTS:
        known = ", ".join(AGENTS)
        raise ValueError(f"Unknown agent: {name} (known: {known})")
    return key


def detect_installed_agents() -> list[str]:
    """Ids of agents detected on this machine (their home dir exists)."""
    return [name for name, spec in AGENTS.items() if spec.installed]
