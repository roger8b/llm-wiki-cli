from __future__ import annotations

from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.services import autolink_service, lint_service
from llmwiki.services.autolink_service import find_mentions


def _titles(*pairs: tuple[str, str]) -> list[tuple[str, str]]:
    return list(pairs)


class TestMatcher:
    def test_links_first_mention_only(self) -> None:
        body = "usamos RAG aqui e RAG ali"
        ms = find_mentions(body, _titles(("RAG", "wiki/concepts/rag.md")), page="wiki/x.md")
        assert len(ms) == 1
        assert ms[0].title == "RAG"

    def test_case_insensitive_match(self) -> None:
        ms = find_mentions("falamos de rag hoje", _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert len(ms) == 1
        assert ms[0].title == "rag"  # preserves prose casing

    def test_word_boundary_no_substring(self) -> None:
        # "RAGTIME" must not match "RAG".
        ms = find_mentions("RAGTIME music", _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert ms == []

    def test_min_length_ignored(self) -> None:
        ms = find_mentions("the ML field", _titles(("ML", "wiki/ml.md")), page="wiki/x.md")
        assert ms == []

    def test_self_link_not_proposed(self) -> None:
        ms = find_mentions(
            "RAG is great", _titles(("RAG", "wiki/concepts/rag.md")), page="wiki/concepts/rag.md"
        )
        assert ms == []

    def test_longest_match_wins(self) -> None:
        body = "Retrieval Augmented Generation rocks"
        titles = _titles(
            ("Retrieval", "wiki/a.md"),
            ("Retrieval Augmented Generation", "wiki/b.md"),
        )
        ms = find_mentions(body, titles, page="wiki/x.md")
        assert len(ms) == 1
        assert ms[0].target == "wiki/b.md"

    def test_skips_code_fence(self) -> None:
        body = "```\nRAG inside code\n```\n"
        ms = find_mentions(body, _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert ms == []

    def test_skips_inline_code(self) -> None:
        ms = find_mentions("use `RAG` carefully", _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert ms == []

    def test_skips_existing_wikilink(self) -> None:
        ms = find_mentions("see [[RAG]] now", _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert ms == []

    def test_skips_markdown_link_and_url(self) -> None:
        body = "[RAG](http://x) and http://rag.io/RAG path"
        ms = find_mentions(body, _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert ms == []

    def test_skips_heading(self) -> None:
        ms = find_mentions("# RAG overview\ntext", _titles(("RAG", "wiki/r.md")), page="wiki/x.md")
        assert ms == []


def _write(brain: BrainPaths, rel: str, text: str) -> None:
    p = brain.wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TestProposeAutolinks:
    def test_dry_run_no_cr_and_lists_mentions(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/rag.md", "---\ntitle: RAG\ntype: concept\n---\n# RAG\nbody\n")
        _write(brain, "concepts/app.md", "---\ntitle: App\ntype: concept\n---\nusamos RAG aqui\n")
        conn = get_connection(brain.db_path)
        try:
            report = autolink_service.propose_autolinks(brain, conn, dry_run=True)
        finally:
            conn.close()
        assert isinstance(report, dict)
        assert report["pages"] == 1
        assert report["mentions"][0]["target"] == "wiki/concepts/rag.md"

    def test_creates_cr_and_result_passes_lint(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/rag.md", "---\ntitle: RAG\ntype: concept\n---\n# RAG\n[[App]]\n")
        _write(brain, "concepts/app.md", "---\ntitle: App\ntype: concept\n---\nusamos RAG aqui\n")
        conn = get_connection(brain.db_path)
        try:
            cr = autolink_service.propose_autolinks(brain, conn)
            assert not isinstance(cr, dict)
            assert cr.files_changed == 1
            # Apply and lint: no new broken links.
            from llmwiki.services import change_request_service

            change_request_service.apply(cr.id, brain, conn)
        finally:
            conn.close()
        findings = lint_service.lint_structural(brain)
        assert not [f for f in findings if f.kind == "broken_link"]
        text = (brain.wiki / "concepts" / "app.md").read_text(encoding="utf-8")
        assert "[[RAG]]" in text

    def test_scope_limits_edited_pages(self, brain: BrainPaths) -> None:
        _write(brain, "concepts/rag.md", "---\ntitle: RAG\ntype: concept\n---\n# RAG\n")
        _write(brain, "entities/x.md", "---\ntitle: X\ntype: entity\n---\nRAG mention here\n")
        _write(brain, "concepts/y.md", "---\ntitle: Y\ntype: concept\n---\nRAG mention here\n")
        conn = get_connection(brain.db_path)
        try:
            report = autolink_service.propose_autolinks(
                brain, conn, scope="entities", dry_run=True
            )
        finally:
            conn.close()
        assert isinstance(report, dict)
        assert {m["page"] for m in report["mentions"]} == {"wiki/entities/x.md"}
