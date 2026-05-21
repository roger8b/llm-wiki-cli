from __future__ import annotations

from llmwiki.core.models import Severity
from llmwiki.core.paths import BrainPaths
from llmwiki.services import lint_service


def _write(brain: BrainPaths, rel: str, text: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _kinds(brain: BrainPaths) -> list[str]:
    return [f.kind for f in lint_service.lint_structural(brain)]


class TestLintStructural:
    def test_detects_broken_link(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/a.md", "---\ntitle: A\ntype: concept\n---\n[[Inexistente]]\n")
        kinds = _kinds(brain)
        assert "broken_link" in kinds

    def test_detects_orphan_page(self, brain: BrainPaths) -> None:
        # b é linkada por a; a não tem entrada → órfã.
        _write(brain, "concepts/a.md", "---\ntitle: A\ntype: concept\n---\n[[B]]\n")
        _write(brain, "concepts/b.md", "---\ntitle: B\ntype: concept\n---\n# B\n")
        findings = lint_service.lint_structural(brain)
        orphans = [f for f in findings if f.kind == "orphan_page"]
        assert [f.pages[0] for f in orphans] == ["wiki/concepts/a.md"]

    def test_detects_missing_frontmatter(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/c.md", "# Sem frontmatter\nlink [[c]]\n")
        assert "missing_frontmatter" in _kinds(brain)

    def test_detects_invalid_type(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/d.md", "---\ntitle: D\ntype: bogus\n---\n[[d]]\n")
        assert "invalid_page_type" in _kinds(brain)

    def test_invalid_frontmatter_is_error_severity(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/e.md", "---\ntitle: : :\n  - x\n---\nbody")
        findings = lint_service.lint_structural(brain)
        bad = [f for f in findings if f.kind == "invalid_frontmatter"]
        assert bad and bad[0].severity == Severity.error
