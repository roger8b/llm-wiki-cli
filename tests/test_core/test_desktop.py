from __future__ import annotations

from llmwiki.core.desktop import read_desktop, update_desktop
from llmwiki.core.paths import BrainPaths


class TestDesktopConfig:
    def test_defaults_when_missing(self, brain: BrainPaths) -> None:
        cfg = read_desktop(brain)
        assert cfg["run_in_background"] is True
        assert cfg["notify_on_jobs"] is True

    def test_update_persists_and_merges(self, brain: BrainPaths) -> None:
        out = update_desktop(brain, {"run_in_background": False})
        assert out["run_in_background"] is False
        assert out["notify_on_jobs"] is True  # untouched default kept
        assert read_desktop(brain)["run_in_background"] is False

    def test_ignores_unknown_and_wrong_type(self, brain: BrainPaths) -> None:
        out = update_desktop(brain, {"run_in_background": "nope", "bogus": 1})
        assert out["run_in_background"] is True  # wrong type ignored
        assert "bogus" not in out

    def test_corrupt_file_falls_back_to_defaults(self, brain: BrainPaths) -> None:
        (brain.dot).mkdir(parents=True, exist_ok=True)
        (brain.dot / "desktop.json").write_text("not json", encoding="utf-8")
        assert read_desktop(brain)["run_in_background"] is True
