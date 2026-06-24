"""Per-job model override + conditional (code-first) self-correction (#279).

A strong model can be pinned to ingestion via ``cfg.models`` without making
``ask`` expensive, and deterministic structural findings are repaired in code
before any LLM fix invocation — so a trivially-fixable staging costs zero fix
passes.
"""

from __future__ import annotations

import json
from pathlib import Path

from llmwiki.core.config import WorkspaceConfig
from llmwiki.core.misc import today
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.llm_agents.factory import resolve_model
from llmwiki.llm_agents.models import IngestionResult
from llmwiki.services import ingest_service
from llmwiki.services.lint_service import autofix_contents


class TestModelOverride:
    def test_operation_override_wins_else_global(self) -> None:
        cfg = WorkspaceConfig(
            brain_root=Path("/tmp/x"),
            model="ollama:llama3.1",
            models={"ingest": "anthropic:MiniMax-M3", "ask": "ollama:llama3.1"},
        )
        assert resolve_model(cfg, "ingest") == "anthropic:MiniMax-M3"
        assert resolve_model(cfg, "ask") == "ollama:llama3.1"
        # maintain has no override -> falls back to the global model.
        assert resolve_model(cfg, "maintain") == "ollama:llama3.1"
        # No operation -> always the global model.
        assert resolve_model(cfg, None) == "ollama:llama3.1"

    def test_no_overrides_is_global_for_every_operation(self) -> None:
        cfg = WorkspaceConfig(brain_root=Path("/tmp/x"), model="ollama:llama3.1")
        for op in ("ingest", "ask", "maintain"):
            assert resolve_model(cfg, op) == "ollama:llama3.1"

    def test_outline_falls_back_to_ingest_then_global(self) -> None:
        # #293: outline is lighter work — its own override wins, else the ingest
        # override, else the global model.
        base = WorkspaceConfig(brain_root=Path("/tmp/x"), model="ollama:llama3.1")
        assert resolve_model(base, "outline") == "ollama:llama3.1"  # nothing pinned

        ingest_only = base.model_copy(update={"models": {"ingest": "anthropic:MiniMax-M3"}})
        assert resolve_model(ingest_only, "outline") == "anthropic:MiniMax-M3"  # inherits ingest

        explicit = base.model_copy(
            update={"models": {"ingest": "anthropic:MiniMax-M3", "outline": "ollama:llama3.1"}}
        )
        assert resolve_model(explicit, "outline") == "ollama:llama3.1"  # own override wins


class TestAutofixContents:
    def test_synthesizes_missing_frontmatter_from_directory(self) -> None:
        files = {"wiki/concepts/rag.md": "# RAG\n\nRetrieval augmented generation.\n"}
        fixed = autofix_contents(files)
        assert "wiki/concepts/rag.md" in fixed
        content = fixed["wiki/concepts/rag.md"]
        assert "type: concept" in content  # inferred from wiki/concepts/
        assert "title: RAG" in content  # from the H1
        assert "updated_at:" in content and today() in content

    def test_corrects_invalid_type_from_directory(self) -> None:
        files = {
            "wiki/entities/openai.md": "---\ntitle: OpenAI\ntype: bogus\n---\n# OpenAI\n",
        }
        fixed = autofix_contents(files)
        assert "type: entity" in fixed["wiki/entities/openai.md"]

    def test_leaves_uninferable_and_valid_pages_untouched(self) -> None:
        files = {
            # No type-bearing directory -> code won't guess.
            "wiki/loose.md": "# Loose\n\nbody\n",
            # Already valid -> not rewritten.
            "wiki/concepts/ok.md": "---\ntitle: OK\ntype: concept\n---\n# OK\n",
            # Broken link is not a deterministic fix -> left for the LLM.
            "wiki/concepts/link.md": "---\ntitle: L\ntype: concept\n---\n# L\n[[Ghost]]\n",
        }
        assert autofix_contents(files) == {}


class TestConditionalSelfCorrection:
    def _src(self, brain: BrainPaths) -> Path:
        src = brain.raw / "articles" / "art.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("about rag", encoding="utf-8")
        return src

    def test_code_fixable_finding_costs_zero_fix_invokes(self, brain: BrainPaths) -> None:
        calls = {"n": 0}

        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            calls["n"] += 1
            # Missing frontmatter — a deterministic, code-fixable finding.
            backend.write("wiki/concepts/rag.md", "# RAG\n\nbody\n")
            return IngestionResult(summary="dirty", new_pages=["wiki/concepts/rag.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                self._src(brain), brain, conn, WorkspaceConfig(brain_root=brain.root),
                runner=runner,
            )
        finally:
            conn.close()

        assert calls["n"] == 1  # the agent was NEVER re-invoked to fix
        assert cr.warnings == []  # the finding was settled in code
        # The staged page now carries synthesized, valid frontmatter.
        content = cr.changes[0].new_content
        assert "type: concept" in content
        assert "updated_at:" in content and today() in content

    def test_meta_records_no_warnings_when_autofixed(self, brain: BrainPaths) -> None:
        def runner(cfg, backend, *, source_path, source_text, source_meta=None, **kw):
            backend.write("wiki/entities/openai.md", "# OpenAI\n\nA lab.\n")
            return IngestionResult(summary="dirty", new_pages=["wiki/entities/openai.md"])

        conn = get_connection(brain.db_path)
        try:
            cr = ingest_service.ingest(
                self._src(brain), brain, conn, WorkspaceConfig(brain_root=brain.root),
                runner=runner,
            )
        finally:
            conn.close()
        meta = json.loads((Path(cr.diff_dir) / "meta.json").read_text(encoding="utf-8"))
        assert meta["warnings"] == []
