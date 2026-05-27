from __future__ import annotations

from pathlib import Path

from llmwiki.services import skills_service


def test_available_lists_shipped_skills() -> None:
    names = skills_service.available()
    assert "wiki-query" in names
    assert "wiki-ingest" in names
    assert "wiki-maintain" in names


def test_install_writes_files_and_manifest(tmp_path: Path) -> None:
    res = skills_service.install(scope="local", root=tmp_path)
    skills_dir = tmp_path / ".claude" / "skills"
    assert res["target"] == str(skills_dir.resolve())
    assert set(res["installed"]) == set(skills_service.available())
    # each skill has its SKILL.md on disk
    for name in res["installed"]:
        assert (skills_dir / name / "SKILL.md").is_file()
    # manifest written with entries
    assert (skills_dir / skills_service.MANIFEST_NAME).is_file()
    listed = skills_service.list_installed(scope="local", root=tmp_path)
    assert {s["name"] for s in listed["skills"]} == set(res["installed"])
    assert all(s["present"] for s in listed["skills"])


def test_doctor_clean_then_detects_modification(tmp_path: Path) -> None:
    skills_service.install(scope="local", root=tmp_path)
    assert skills_service.doctor(scope="local", root=tmp_path)["ok"] is True

    # tamper with an installed skill
    md = tmp_path / ".claude" / "skills" / "wiki-query" / "SKILL.md"
    md.write_text(md.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    report = skills_service.doctor(scope="local", root=tmp_path)
    assert report["ok"] is False
    assert any(i["skill"] == "wiki-query" and i["issue"] == "modified" for i in report["issues"])


def test_doctor_detects_missing(tmp_path: Path) -> None:
    skills_service.install(scope="local", root=tmp_path)
    (tmp_path / ".claude" / "skills" / "wiki-ingest" / "SKILL.md").unlink()
    report = skills_service.doctor(scope="local", root=tmp_path)
    assert any(i["skill"] == "wiki-ingest" and i["issue"] == "missing" for i in report["issues"])


def test_remove_one_and_all(tmp_path: Path) -> None:
    skills_service.install(scope="local", root=tmp_path)
    skills_service.remove("wiki-maintain", scope="local", root=tmp_path)
    listed = skills_service.list_installed(scope="local", root=tmp_path)
    names = {s["name"] for s in listed["skills"]}
    assert "wiki-maintain" not in names
    assert not (tmp_path / ".claude" / "skills" / "wiki-maintain").exists()

    skills_service.remove(scope="local", root=tmp_path)  # all
    assert skills_service.list_installed(scope="local", root=tmp_path)["skills"] == []


def test_unknown_agent_and_scope_raise(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        skills_service.resolve_skills_dir(agent="bogus", root=tmp_path)
    with pytest.raises(ValueError):
        skills_service.resolve_skills_dir(scope="bogus", root=tmp_path)
