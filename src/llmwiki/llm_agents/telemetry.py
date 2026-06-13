"""Execution telemetry for agent runs (epic #119).

A small, side-channel record of *how* an agent run went — which model, how many
tokens, how long, how many tool calls, and whether the structured-output
fallback had to kick in. Captured in ``factory`` around ``agent.invoke`` and
surfaced in the change request's ``meta.json`` and the job result, so quality
regressions across providers can be audited after the fact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ExecutionMeta:
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    latency_ms: int = 0
    used_fallback: bool = False

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
        return ExecutionMeta(
            model=metas[0].model,
            tokens_in=sum(m.tokens_in for m in metas),
            tokens_out=sum(m.tokens_out for m in metas),
            tool_calls=sum(m.tool_calls for m in metas),
            latency_ms=sum(m.latency_ms for m in metas),
            used_fallback=any(m.used_fallback for m in metas),
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
    )
