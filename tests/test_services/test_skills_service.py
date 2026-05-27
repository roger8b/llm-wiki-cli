from __future__ import annotations

from pathlib import Path

import pytest

from llmwiki.services import skills_service as ss


def test_available_lists_shipped_skills() -> None:
    names = ss.available()
    assert {"wiki-query", "wiki-ingest", "wiki-maintain"} <= set(names)


def test_install_symlinks_into_store(tmp_path: Path) -> None:
    res = ss.install(agent="claude", scope="local", method="symlink", root=tmp_path)
    skills_dir = tmp_path / ".claude" / "skills"
    # central store populated (WIKI_HOME isolated to tmp by conftest)
    store = Path(res["store"])
    assert (store / "wiki-query" / "SKILL.md").is_file()
    # each skill is a symlink in the agent dir pointing at the store
    for name in ss.available():
        link = skills_dir / name
        assert link.is_symlink()
        assert (link / "SKILL.md").is_file()  # resolves through the symlink

    listed = ss.list_installed()
    assert len(listed["installs"]) == 1
    statuses = listed["installs"][0]["skills_status"]
    assert all(s["present"] and s["symlink"] for s in statuses)
    assert ss.doctor()["ok"] is True


def test_multi_agent_dedup_dests(tmp_path: Path) -> None:
    # gemini + cursor share .agents/skills -> one dest; claude has its own
    res = ss.install(agents=["claude", "gemini", "cursor"], scope="local", root=tmp_path)
    dests = {r["dest"] for r in res["results"]}
    assert len(dests) == 2  # .claude/skills + .agents/skills (gemini+cursor shared)


def test_doctor_detects_broken_symlink(tmp_path: Path) -> None:
    res = ss.install(agent="claude", scope="local", root=tmp_path)
    # delete the store target -> dangling symlinks
    import shutil

    shutil.rmtree(Path(res["store"]) / "wiki-query")
    issues = ss.doctor()["issues"]
    assert any(i["issue"] == "broken-symlink" and i["skill"] == "wiki-query" for i in issues)


def test_copy_method(tmp_path: Path) -> None:
    ss.install(agent="claude", scope="local", method="copy", root=tmp_path)
    link = tmp_path / ".claude" / "skills" / "wiki-query"
    assert link.is_dir() and not link.is_symlink()


def test_remove_unlinks_but_keeps_store(tmp_path: Path) -> None:
    res = ss.install(agent="claude", scope="local", root=tmp_path)
    store = Path(res["store"])
    ss.remove()  # all
    assert not (tmp_path / ".claude" / "skills" / "wiki-query").exists()
    assert ss.list_installed()["installs"] == []
    # store is the source of truth — never deleted
    assert (store / "wiki-query" / "SKILL.md").is_file()


def test_unknown_agent_and_method_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ss.install(agent="bogus", scope="local", root=tmp_path)
    with pytest.raises(ValueError):
        ss.install(agent="claude", method="bogus", scope="local", root=tmp_path)
