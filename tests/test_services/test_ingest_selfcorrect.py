"""Pre-CR structural self-correction loop in ingestion (#166)."""

from __future__ import annotations

import json
from pathlib import Path

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import ingest_service

GOOD = "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n# RAG\nBody.\n"
# A broken wikilink is a finding code can't settle deterministically (#279), so
# it still drives the LLM fix loop. (missing_frontmatter is now auto-fixed in
# code — see test_ingest_conditional_fix.py.)
BAD = (
    "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n# RAG\nSee [[Ghost Page]].\n"
)


def _src(brain: BrainPaths, text: str = "about rag") -> Path:
    src = brain.raw / "articles" / "art.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(text, encoding="utf-8")
    return src


def _cfg(brain: BrainPaths) -> WorkspaceConfig:
    return WorkspaceConfig(brain_root=brain.root)


def _meta(cr) -> dict:
    return json.loads((Path(cr.diff_dir) / "meta.json").read_text(encoding="utf-8"))


class TestSelfCorrect:
    def test_clean_staging_single_invocation(self, brain: BrainPaths) -> None:
        calls = {"n": 0}

        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            calls["n"] += 1
            backend.write("wiki/concepts/rag.md", GOOD)
            return IngestionResult(summary="ok", new_pages=["wiki/concepts/rag.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(_src(brain), brain, conn, _cfg(brain), runner=runner)
        finally:
            conn.close()
        assert calls["n"] == 1  # no extra cost when clean
        assert cr.warnings == []
        assert _meta(cr)["warnings"] == []

    def test_dirty_then_fixed_no_warnings(self, brain: BrainPaths) -> None:
        calls = {"n": 0}
        received: list = []

        def runner(
            cfg, backend, *, source_path, source_text, source_meta=None,
            fix_findings=None, **kw,
        ):
            calls["n"] += 1
            received.append(fix_findings)
            if fix_findings is None:
                backend.write("wiki/concepts/rag.md", BAD)  # first pass: dirty
                return IngestionResult(summary="dirty", new_pages=["wiki/concepts/rag.md"])
            backend.write("wiki/concepts/rag.md", GOOD)  # fix pass: clean
            return IngestionResult(summary="fixed")

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(_src(brain), brain, conn, _cfg(brain), runner=runner)
        finally:
            conn.close()
        assert calls["n"] == 2  # one fix pass
        assert received[1] and any("broken_link" in f for f in received[1])
        assert cr.warnings == []
        assert cr.changes[0].new_content == GOOD

    def test_persistent_issue_becomes_warning(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            backend.write("wiki/concepts/rag.md", BAD)  # never fixed
            return IngestionResult(summary="dirty", new_pages=["wiki/concepts/rag.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(_src(brain), brain, conn, _cfg(brain), runner=runner)
        finally:
            conn.close()
        assert cr.warnings and any("broken_link" in w for w in cr.warnings)
        assert _meta(cr)["warnings"] == cr.warnings

    def test_retries_zero_disables_loop(self, brain: BrainPaths) -> None:
        calls = {"n": 0}

        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            calls["n"] += 1
            backend.write("wiki/concepts/rag.md", BAD)
            return IngestionResult(summary="dirty", new_pages=["wiki/concepts/rag.md"])

        cfg = _cfg(brain)
        cfg.agent_fix_retries = 0
        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(_src(brain), brain, conn, cfg, runner=runner)
        finally:
            conn.close()
        assert calls["n"] == 1  # no fix pass attempted
        assert cr.warnings and any("broken_link" in w for w in cr.warnings)

    def test_sibling_link_in_staging_not_flagged(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            backend.write(
                "wiki/concepts/rag.md",
                "---\ntitle: RAG\ntype: concept\n---\n# RAG\nSee [[Vector Store]].\n",
            )
            backend.write(
                "wiki/concepts/vector-store.md",
                "---\ntitle: Vector Store\ntype: concept\n---\n# Vector Store\n",
            )
            return IngestionResult(
                summary="two",
                new_pages=["wiki/concepts/rag.md", "wiki/concepts/vector-store.md"],
            )

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(_src(brain), brain, conn, _cfg(brain), runner=runner)
        finally:
            conn.close()
        assert cr.warnings == []  # the [[Vector Store]] link resolves in staging
