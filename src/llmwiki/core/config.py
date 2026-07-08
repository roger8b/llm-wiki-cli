"""Global workspace configuration, stored at ``~/.wiki/config.yaml``.

The config file is shared across all brains on this machine. It is created
once (on the first ``wiki init``) and never overwritten by subsequent inits,
so the user's customisations are preserved.

Per-brain overrides are not currently supported; if needed in the future they
can be layered on top (brain-local config shadows global config).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from . import paths as _paths_module
from .paths import BrainPaths

# Fields that live in ~/.wiki/config.yaml (persisted + editable via the API).
# NOTE: API keys are NOT here — they live in the OS keychain (core.secrets).
_CONFIG_KEYS = (
    "model",
    "fts_limit",
    "num_ctx",
    "temperature",
    "request_timeout",
    "agent_max_retries",
    "ingest_max_retries",
    "agent_fix_retries",
    "max_output_tokens",
    "max_output_tokens_by_op",
    "onboarded",
    "providers",
    "models",
    "whisper_model",
    "whisper_language",
    "chunk_threshold_chars",
    "chunk_size_chars",
    "chunk_overlap_chars",
    "ingest_chunk_concurrency",
    "ingest_prefetch_candidates",
    "ingest_scope_concepts_per_chunk",
    "ingest_exclude_builtin_tools",
    "embedding_model",
    "ask_mode",
    "ask_rag_top_k",
    "ask_rag_max_context_chars",
    "ask_history_turns",
    "ask_history_max_chars",
    "lint_token_budget",
    "worker_concurrency",
    "curation_interval_hours",
    "curation_semantic",
)

# Default config written on first init.
_DEFAULTS: dict[str, object] = {
    "model": "ollama:llama3.1",
    "fts_limit": 20,
    "num_ctx": 8192,
    "temperature": None,
    "request_timeout": 300,
    "agent_max_retries": 2,
    "ingest_max_retries": None,
    # Self-correction passes for structural lint findings before the CR (#166).
    "agent_fix_retries": 1,
    # Output-token cap (#351). None/0 = no cap (provider default, current
    # behaviour). Per-op overrides ("ingest", "ask", "maintain", "outline")
    # win over the global; "outline" falls back to "ingest" (#293 chain).
    "max_output_tokens": None,
    "max_output_tokens_by_op": {},
    "onboarded": False,
    "providers": {},
    # Optional per-operation model override (#279). Empty = single global model.
    "models": {},
    "whisper_model": "small",
    "whisper_language": None,
    # Long-source multi-pass ingestion (#162). Sources longer than the
    # threshold are split into chunks and ingested pass-by-pass.
    "chunk_threshold_chars": 24000,
    "chunk_size_chars": 16000,
    "chunk_overlap_chars": 1000,
    # Parallel chunk passes for long-source ingestion (#277). 1 = serial (the
    # legacy shared-backend behaviour); >1 runs chunk passes concurrently.
    "ingest_chunk_concurrency": 3,
    # Pre-fetch top-K existing pages per outline concept (#292). 0 disables.
    "ingest_prefetch_candidates": 3,
    # Scope outline concepts to the chunk text that mentions them (#294).
    "ingest_scope_concepts_per_chunk": True,
    # Hide unused DeepAgents built-ins on the ingestion agent (#334). False =
    # legacy (only execute hidden).
    "ingest_exclude_builtin_tools": True,
    # Local semantic search (#169). None = disabled (pure FTS). Format
    # "<provider>:<model>", e.g. "ollama:nomic-embed-text".
    "embedding_model": None,
    # Ask path (#350): "agent" = legacy agent loop (default, identical
    # behaviour); "rag" = retrieve top-k in code + ONE LLM call, no tools;
    # "auto" = try rag, fall back to the agent path at most once.
    "ask_mode": "agent",
    "ask_rag_top_k": 6,
    "ask_rag_max_context_chars": 24000,
    # Ask follow-up window (#190): how many prior turns of the conversation to
    # feed back as context, and the char cap on that block (long answers
    # truncated with "…").
    "ask_history_turns": 4,
    "ask_history_max_chars": 8000,
    # Semantic lint in batches (#173): total estimated-token budget per
    # `wiki lint --all` run. Batches that don't fit are deferred and reported.
    "lint_token_budget": 60000,
    "worker_concurrency": 1,
    "curation_interval_hours": None,
    "curation_semantic": True,
}


class ProviderConfig(BaseModel):
    """Non-secret per-provider settings (the API key lives in the keychain)."""

    base_url: str | None = None
    model: str | None = None


class WorkspaceConfig(BaseModel):
    brain_root: Path
    model: str = "ollama:llama3.1"
    fts_limit: int = 20
    # LLM tuning (primarily for local Ollama models)
    num_ctx: int = 8192  # context window in tokens
    temperature: float | None = None  # None = provider default
    request_timeout: int = 300  # seconds
    # Total agent.invoke attempts on transient errors (1 = no retry).
    agent_max_retries: int = 2
    # Ingestion-only override of agent_max_retries (#291). None = inherit it.
    # Lets ingestion cap retries (a strong model rarely needs them) without
    # changing ``ask``'s retry budget.
    ingest_max_retries: int | None = None
    # Max self-correction passes when staging has structural lint findings
    # before the change request is created (#166); 0 disables the loop.
    agent_fix_retries: int = 1
    # Output-token cap per LLM call (#351). None or 0 = no cap (byte-identical
    # to the previous behaviour). ``max_output_tokens_by_op`` overrides the
    # global per operation ("ingest"/"ask"/"maintain"/"outline"); "outline"
    # inherits the "ingest" override, same chain as ``models`` (#293).
    max_output_tokens: int | None = None
    max_output_tokens_by_op: dict[str, int] = {}
    # True once the user has completed the first-run onboarding flow.
    onboarded: bool = False
    # Per-provider settings keyed by provider name (openai|anthropic|google).
    providers: dict[str, ProviderConfig] = {}
    # Per-operation model override (#279). Keys: "ingest", "ask", "maintain".
    # An absent operation falls back to ``model`` — so a strong model can drive
    # ingestion without making ``ask`` expensive. Format "<provider>:<model>".
    models: dict[str, str] = {}
    # Offline audio transcription (faster-whisper, optional [audio] extra).
    whisper_model: str = "small"  # tiny|base|small|medium|large-v3
    whisper_language: str | None = None  # None = autodetect
    # Multi-pass ingestion for long sources (#162). A source longer than
    # ``chunk_threshold_chars`` is split into ``chunk_size_chars`` windows with
    # ``chunk_overlap_chars`` of overlap and ingested one chunk at a time,
    # reusing the same change-request backend so later chunks see earlier pages.
    chunk_threshold_chars: int = 24000
    chunk_size_chars: int = 16000
    chunk_overlap_chars: int = 1000
    # Parallel chunk passes for long sources (#277). 1 = serial (legacy shared
    # backend; chunk N sees pages staged by N-1). >1 runs passes concurrently on
    # isolated backends, merged deterministically (lowest chunk index wins a path
    # collision) — for long multi-chunk sources this is the main latency win.
    ingest_chunk_concurrency: int = 3
    # Pre-fetch existing pages per outline concept before the chunk passes (#292).
    # The outline already lists the source's concepts; running one hybrid search
    # per concept IN CODE lets each chunk decide edit-vs-create from the message
    # instead of spending sequential search_pages/related_pages tool round-trips.
    # 0 disables (legacy behaviour: the agent discovers pages via tool calls).
    ingest_prefetch_candidates: int = 3
    # Scope outline concepts to the chunk text that mentions them (#294). False
    # keeps the previous behaviour: every chunk receives the full outline.
    ingest_scope_concepts_per_chunk: bool = True
    # Hide the DeepAgents built-ins ingestion never uses — write_todos/task/glob/
    # grep/ls (#334). Their schemas were re-sent every turn, inflating
    # system_framework. False reproduces the legacy behaviour (only execute hidden).
    ingest_exclude_builtin_tools: bool = True
    # Local semantic search (#169, optional [semantic] extra). None disables it
    # entirely (pure FTS). "<provider>:<model>", e.g. "ollama:nomic-embed-text".
    embedding_model: str | None = None
    # Single-shot RAG ask (#350). "agent" (default) = legacy loop, byte
    # identical; "rag" = hybrid_search top-k in code + one structured LLM call
    # without tools; "auto" = rag first, one agent fallback on 0 hits or
    # invalid citations. Unknown values degrade to "agent".
    ask_mode: str = "agent"
    ask_rag_top_k: int = 6
    ask_rag_max_context_chars: int = 24000
    # Ask follow-up conversation window (#190).
    ask_history_turns: int = 4
    ask_history_max_chars: int = 8000
    # Semantic lint batching (#173). Total estimated-token budget per
    # ``wiki lint --all`` run; batches over budget are deferred and reported.
    lint_token_budget: int = 60000
    # Background worker concurrency (#140, ADR 001). 1 = single-threaded (byte
    # for byte the legacy behaviour). >1 enables a read/write split: write jobs
    # (ingest/maintain) stay serialized while reads (ask/lint) run concurrently.
    worker_concurrency: int = 1
    # Scheduled curator (#41). None disables the auto-run; the backend checks
    # hourly whether now - last_curation_at > interval. `wiki curate` always
    # works manually. curation_semantic toggles the (costly) semantic lint pass.
    curation_interval_hours: int | None = None
    curation_semantic: bool = True
    # Auto-enqueue a background reindex when the startup drift check detects
    # db×disk divergence (#308). True = self-heal; False = record the drift
    # to meta kv and let the UI/CLI surface a manual reindex button.
    index_autorebuild_on_drift: bool = True

    @property
    def paths(self) -> BrainPaths:
        return BrainPaths(root=self.brain_root)


def _config_file() -> Path:
    """Global config path: ~/.wiki/config.yaml

    Reading via module attribute so tests can monkeypatch
    ``llmwiki.core.paths.WIKI_HOME`` to redirect to a temp dir.
    """
    return _paths_module.WIKI_HOME / "config.yaml"


def _read_global_config() -> dict[str, object]:
    """Raw global config dict (no brain required). Empty if absent/invalid."""
    cfg_path = _config_file()
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    return {}


def load_config(paths: BrainPaths) -> WorkspaceConfig:
    """Load global config; fall back to defaults for missing fields."""
    cfg_path = _config_file()
    data: dict[str, object] = {}
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data["brain_root"] = paths.root
    return WorkspaceConfig.model_validate(data)


def write_default_config(paths: BrainPaths) -> None:  # noqa: ARG001
    """Write ~/.wiki/config.yaml with defaults if it doesn't exist yet.

    The ``paths`` argument is kept for API compatibility but is no longer used
    (config is now global, not per-brain).
    """
    cfg_path = _config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists():
        # Preserve the user's existing config — never overwrite.
        return
    cfg_path.write_text(
        yaml.safe_dump(_DEFAULTS, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def update_config(patch: dict[str, object]) -> None:
    """Merge ``patch`` into ~/.wiki/config.yaml, preserving other keys.

    Only known fields (``model``, ``fts_limit``) are persisted; unknown keys
    are ignored to keep the file clean.
    """
    cfg_path = _config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = dict(_DEFAULTS)
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = {**_DEFAULTS, **loaded}
    for key in _CONFIG_KEYS:
        if key not in patch:
            continue
        if key == "providers" and isinstance(patch[key], dict):
            # deep-merge per-provider settings instead of replacing the map
            providers_val = data.get("providers")
            current: dict[str, object] = (
                dict(providers_val) if isinstance(providers_val, dict) else {}
            )
            patch_providers = patch[key]
            assert isinstance(patch_providers, dict)
            for prov, settings in patch_providers.items():
                prov_val = current.get(prov)
                merged: dict[str, object] = (
                    dict(prov_val) if isinstance(prov_val, dict) else {}
                )
                if isinstance(settings, dict):
                    merged.update(settings)
                current[prov] = merged
            data["providers"] = current
        else:
            data[key] = patch[key]  # allow None (e.g. temperature) explicitly
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
