"""Execution telemetry for agent runs (epic #119).

A small, side-channel record of *how* an agent run went — which model, how many
tokens, how long, how many tool calls, and whether the structured-output
fallback had to kick in. Captured in ``factory`` around ``agent.invoke`` and
surfaced in the change request's ``meta.json`` and the job result, so quality
regressions across providers can be audited after the fact.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

# Search tools whose output rides the agent history (re-sent each turn) — the
# direct target of token-cost work (#309, #321).
_SEARCH_TOOLS = frozenset({"search_pages", "search_by_type"})
_RELATED_TOOLS = frozenset({"related_pages"})


@dataclass
class ExecutionMeta:
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    latency_ms: int = 0
    used_fallback: bool = False
    # Input tokens attributed by origin, accounting for re-send (#321). Keys:
    # system / document / search_tool / related_tool / assistant_history / other.
    tokens_by_source: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def merge(metas: list[ExecutionMeta]) -> ExecutionMeta | None:
        """Aggregate per-pass telemetry into one record (multi-pass ingest, #162).

        Sums tokens/latency/tool_calls, keeps the first model seen, and ORs the
        fallback flag (any pass falling back marks the whole run). Returns
        ``None`` for an empty list so callers can persist ``None`` unchanged.
        """
        if not metas:
            return None
        by_source: dict[str, int] = {}
        for m in metas:
            for src, n in m.tokens_by_source.items():
                by_source[src] = by_source.get(src, 0) + n
        return ExecutionMeta(
            model=metas[0].model,
            tokens_in=sum(m.tokens_in for m in metas),
            tokens_out=sum(m.tokens_out for m in metas),
            tool_calls=sum(m.tool_calls for m in metas),
            latency_ms=sum(m.latency_ms for m in metas),
            used_fallback=any(m.used_fallback for m in metas),
            tokens_by_source=by_source,
        )


def extract_meta(
    state: dict[str, Any],
    *,
    model: str,
    latency_ms: int,
    used_fallback: bool,
) -> ExecutionMeta:
    """Build an ``ExecutionMeta`` from the agent's final ``state``.

    Sums ``usage_metadata`` and counts ``tool_calls`` across every AI message in
    the conversation. All extraction is best-effort: missing fields default to 0
    so telemetry never breaks a run.
    """
    tokens_in = 0
    tokens_out = 0
    tool_calls = 0
    for msg in state.get("messages", []):
        usage = getattr(msg, "usage_metadata", None)
        if isinstance(usage, dict):
            tokens_in += int(usage.get("input_tokens", 0) or 0)
            tokens_out += int(usage.get("output_tokens", 0) or 0)
        calls = getattr(msg, "tool_calls", None)
        if calls:
            tool_calls += len(calls)
    return ExecutionMeta(
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tool_calls=tool_calls,
        latency_ms=latency_ms,
        used_fallback=used_fallback,
        tokens_by_source=tokens_by_source(
            state.get("messages", []), total_input_tokens=tokens_in
        ),
    )


def _classify(msg: Any) -> str:
    """Bucket a message by origin for input-token attribution (#321)."""
    mtype = getattr(msg, "type", None)
    if mtype == "system":
        return "system"
    if mtype == "human":
        return "document"
    if mtype == "ai":
        return "assistant_history"
    if mtype == "tool":
        name = getattr(msg, "name", None)
        if name in _SEARCH_TOOLS:
            return "search_tool"
        if name in _RELATED_TOOLS:
            return "related_tool"
    return "other"


def _default_tokenize(text: str) -> int:
    """tiktoken token count; ``len // 4`` fallback when unavailable. Best-effort:
    only the ratio between buckets matters, so a rough count for non-OpenAI
    models is fine and a missing tokenizer must never break a run (#321)."""
    try:
        import tiktoken  # noqa: PLC0415

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:  # noqa: BLE001 — telemetry never breaks the run
        return len(text) // 4


def tokens_by_source(
    messages: list[Any],
    *,
    total_input_tokens: int | None = None,
    tokenize: Callable[[str], int] | None = None,
) -> dict[str, int]:
    """Attribute input tokens to each message origin, counting re-send (#321).

    The real cost of a message is paid once per model invoke whose prompt
    includes it: in a multi-turn agent every prior message is re-sent on the
    next turn. So each message's token count is multiplied by the number of
    invokes (AI messages carrying ``usage_metadata``) that occur after it. The
    bucket totals therefore approximate ``tokens_in`` (Σ prompt tokens per
    invoke), split by where those tokens came from. Empty when there are no
    invokes (nothing was ever sent).

    The agent's system prompt is injected by the framework below the message
    list, so it is not visible here. When ``total_input_tokens`` (the provider's
    authoritative ``tokens_in``) is given, the unattributed remainder — system
    prompt re-sent each turn plus chat-template/tokenizer overhead — is recorded
    as ``system_framework`` so the buckets reconcile exactly with ``tokens_in``.
    """
    tok = tokenize or _default_tokenize
    invoke_positions = [
        i
        for i, m in enumerate(messages)
        if isinstance(getattr(m, "usage_metadata", None), dict)
    ]
    if not invoke_positions:
        return {}

    result: dict[str, int] = {}
    for j, msg in enumerate(messages):
        remaining = sum(1 for p in invoke_positions if p > j)
        if remaining == 0:
            continue
        content = getattr(msg, "content", "")
        n = tok(content if isinstance(content, str) else str(content)) * remaining
        if n:
            bucket = _classify(msg)
            result[bucket] = result.get(bucket, 0) + n

    if total_input_tokens is not None:
        residual = total_input_tokens - sum(result.values())
        if residual > 0:
            result["system_framework"] = result.get("system_framework", 0) + residual
    return result
