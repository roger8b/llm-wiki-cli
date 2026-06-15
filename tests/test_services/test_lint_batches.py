from __future__ import annotations

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.models import LintFinding, Severity
from llmwiki.core.paths import BrainPaths
from llmwiki.services import lint_service
from llmwiki.services.lint_service import Batch


def _write(brain: BrainPaths, rel: str, text: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _cfg(brain: BrainPaths, budget: int) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root, lint_token_budget=budget)


def _seed_three_types(brain: BrainPaths) -> None:
    _write(brain, "concepts/a.md", "---\ntitle: A\ntype: concept\n---\nbody a\n")
    _write(brain, "entities/b.md", "---\ntitle: B\ntype: entity\n---\nbody b\n")
    _write(brain, "decisions/c.md", "---\ntitle: C\ntype: decision\n---\nbody c\n")


class TestPartition:
    def test_three_types_make_three_batches(self, brain: BrainPaths) -> None:
        _seed_three_types(brain)
        to_run, skipped = lint_service.partition_pages(brain, budget=1_000_000)
        assert [b.name for b in to_run] == ["concepts", "decisions", "entities"]
        assert skipped == []
        # Each batch carries the explicit page list.
        assert to_run[0].pages == ["wiki/concepts/a.md"]

    def test_scope_restricts_to_one_dir(self, brain: BrainPaths) -> None:
        _seed_three_types(brain)
        to_run, skipped = lint_service.partition_pages(
            brain, budget=1_000_000, scope="concepts"
        )
        assert [b.name for b in to_run] == ["concepts"]
        assert skipped == []

    def test_tight_budget_defers_excess_no_page_dropped(self, brain: BrainPaths) -> None:
        # Each file ~40 chars → ~10 tokens. Budget 12 fits one batch only.
        _seed_three_types(brain)
        to_run, skipped = lint_service.partition_pages(brain, budget=12)
        assert len(to_run) == 1
        assert len(skipped) == 2
        # No page silently ignored: union of run+skipped == all pages.
        covered = {p for b in to_run + skipped for p in b.pages}
        assert covered == {
            "wiki/concepts/a.md",
            "wiki/entities/b.md",
            "wiki/decisions/c.md",
        }

    def test_oversized_dir_splits_alphabetically(self, brain: BrainPaths) -> None:
        big = "x" * 400  # ~100 tokens each
        _write(brain, "concepts/a.md", f"---\ntitle: A\ntype: concept\n---\n{big}\n")
        _write(brain, "concepts/b.md", f"---\ntitle: B\ntype: concept\n---\n{big}\n")
        to_run, _ = lint_service.partition_pages(brain, budget=120)
        # First sub-batch runs; second deferred under total budget.
        assert to_run[0].pages == ["wiki/concepts/a.md"]


class TestConsolidate:
    def test_duplicate_findings_merged_keeping_highest_severity(self) -> None:
        f1 = LintFinding(
            kind="contradiction", severity=Severity.warn, message="m", pages=["x", "y"]
        )
        f2 = LintFinding(
            kind="contradiction", severity=Severity.error, message="m", pages=["y", "x"]
        )
        out = lint_service._consolidate([f1, f2])
        assert len(out) == 1
        assert out[0].severity == Severity.error


class TestLintBatched:
    def test_runner_receives_explicit_page_lists(self, brain: BrainPaths) -> None:
        _seed_three_types(brain)
        seen: list[list[str]] = []

        def fake_runner(cfg: WorkspaceConfig, batch: Batch) -> list[LintFinding]:
            seen.append(batch.pages)
            return [
                LintFinding(
                    kind="gap", severity=Severity.info, message=batch.name, pages=batch.pages
                )
            ]

        report = lint_service.lint_batched(
            brain, _cfg(brain, 1_000_000), batch_runner=fake_runner
        )
        assert seen == [
            ["wiki/concepts/a.md"],
            ["wiki/decisions/c.md"],
            ["wiki/entities/b.md"],
        ]
        assert len(report.processed) == 3
        assert report.skipped == []
        assert any(f.kind == "gap" for f in report.findings)

    def test_tight_budget_reports_skipped(self, brain: BrainPaths) -> None:
        _seed_three_types(brain)

        def fake_runner(cfg: WorkspaceConfig, batch: Batch) -> list[LintFinding]:
            return []

        report = lint_service.lint_batched(
            brain, _cfg(brain, 12), batch_runner=fake_runner
        )
        assert len(report.processed) == 1
        assert len(report.skipped) == 2
