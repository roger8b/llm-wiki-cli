"""MinimalRunner — thin native tool-calling loop, no DeepAgents (#352).

Core-swap experiment behind the ``Runner`` seam (epic #348, H6): the baseline
showed ``system_framework`` (framework prompt + built-in tool schemas re-sent
every turn) at 47–81% of tokens_in. This loop keeps ONLY what the ingestion
actually uses: the ``ingestion.md`` prompt, the domain tools, the backend's
file tools and a final ``submit_result`` tool for structured output.

Invariants preserved (spec of #352):
- staging/dedup/path guards: all writes go through ``ChangeRequestBackend``;
- cooperative cancellation: ``backend.cancel_check`` probed every turn;
- telemetry: ``ExecutionMeta`` (tokens, tool_calls, tokens_by_source #321)
  stashed on ``backend.execution_meta``;
- retry/backoff on transient model errors (same policy as ``_invoke_with_retry``);
- #291 parity: JSON-in-text coercion before the degraded fallback.

Selected via ``cfg.agent_core = "minimal"`` — default stays ``"deepagents"``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..core.config import WorkspaceConfig
from .backend import ChangeRequestBackend
from .models import IngestionResult, OutlinePlan
from .telemetry import extract_meta

logger = logging.getLogger("llmwiki.llm_agents.minimal")

_SUBMIT_TOOL = {
    "name": "submit_result",
    "description": (
        "Entrega o resultado estruturado FINAL da ingestão. Chame UMA vez, "
        "depois de escrever todas as páginas com write_file/edit_file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Resumo do que foi integrado."},
            "new_pages": {"type": "array", "items": {"type": "string"}},
            "affected_pages": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary"],
    },
}


def _file_tools(backend: ChangeRequestBackend) -> dict[str, Any]:
    """Backend-bound file tools; every write rides the staging guardrails."""

    def write_file(file_path: str, content: str) -> str:
        res = backend.write(file_path, content)
        return res.error or f"ok: {file_path} escrito."

    def edit_file(
        file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        res = backend.edit(file_path, old_string, new_string, replace_all)
        return res.error or f"ok: {file_path} editado."

    def read_file(file_path: str, offset: int = 0, limit: int = 2000) -> str:
        res = backend.read(file_path, offset, limit)
        if res.error:
            return str(res.error)
        data: Any = res.file_data or {}
        return str(data.get("content", "")) if isinstance(data, dict) else str(data)

    return {"write_file": write_file, "edit_file": edit_file, "read_file": read_file}


def _tool_specs(tools: dict[str, Any]) -> list[dict[str, Any]]:
    """OpenAI-style tool schemas from the plain callables' signatures."""
    import inspect

    specs: list[dict[str, Any]] = []
    for name, fn in tools.items():
        props: dict[str, Any] = {}
        required: list[str] = []
        for pname, param in inspect.signature(fn).parameters.items():
            ptype = {int: "integer", bool: "boolean"}.get(param.annotation, "string")
            props[pname] = {"type": ptype}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        specs.append(
            {
                "name": name,
                "description": (fn.__doc__ or name).strip(),
                "parameters": {"type": "object", "properties": props, "required": required},
            }
        )
    return specs


def _check_cancel(backend: ChangeRequestBackend) -> None:
    from ..core.errors import JobCancelledError

    if backend.cancel_check is not None and backend.cancel_check():
        raise JobCancelledError("cancelled during minimal agent loop")


def _invoke_with_retry(model: Any, messages: list[Any], cfg: WorkspaceConfig) -> AIMessage:
    from ..core.errors import JobCancelledError

    attempts = max(1, cfg.ingest_max_retries or cfg.agent_max_retries)
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            out = model.invoke(messages)
            assert isinstance(out, AIMessage)
            return out
        except JobCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — same transient policy as factory
            last = exc
            if attempt >= attempts:
                break
            backoff = min(2.0 ** (attempt - 1), 8.0)
            logger.warning(
                "minimal model.invoke failed (%d/%d): %s — retry in %.1fs",
                attempt,
                attempts,
                exc,
                backoff,
            )
            time.sleep(backoff)
    assert last is not None
    raise last


def _coerce_result(messages: list[Any]) -> IngestionResult | None:
    """#291 parity: recover an IngestionResult from JSON emitted as text."""
    from .factory import _coerce_from_messages

    return _coerce_from_messages({"messages": messages}, IngestionResult)


def run_ingestion_minimal(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
    outline: OutlinePlan | None = None,
    part: tuple[int, int] | None = None,
    fix_findings: list[str] | None = None,
    model: Any | None = None,
) -> IngestionResult:
    """Drop-in ``Runner`` with a native tool-calling loop (no DeepAgents).

    ``model`` is injectable for tests; production builds it from the config
    (same per-operation resolution as the DeepAgents path).
    """
    from .factory import _build_model, _fix_message, _ingestion_message, _prompt
    from .tools import domain_tools

    start = time.perf_counter()
    if model is None:
        model = _build_model(cfg, "ingest")

    tools: dict[str, Any] = {fn.__name__: fn for fn in domain_tools(cfg.paths, cfg)}
    tools.update(_file_tools(backend))
    specs = _tool_specs(tools)
    bound = model.bind_tools([*specs, _SUBMIT_TOOL])

    if fix_findings:
        message = _fix_message(fix_findings)
    else:
        # Prefetch parity with the DeepAgents path (#292).
        from .factory import prefetch_candidates

        candidates = (
            prefetch_candidates(cfg, outline.concepts, limit=cfg.ingest_prefetch_candidates)
            if outline is not None and cfg.ingest_prefetch_candidates > 0
            else None
        )
        message = _ingestion_message(
            cfg,
            source_path=source_path,
            source_text=source_text,
            source_meta=source_meta,
            outline=outline,
            part=part,
            candidates=candidates,
            scoped_concepts=cfg.ingest_scope_concepts_per_chunk,
        )
    system = (
        _prompt("ingestion.md")
        + "\n\nAo terminar TODAS as escritas, chame a tool `submit_result` com o "
        "resultado estruturado. Não devolva o resultado como texto."
    )
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=message)]

    result: IngestionResult | None = None
    used_fallback = False
    max_turns = max(1, cfg.minimal_max_turns)
    for _turn in range(max_turns):
        _check_cancel(backend)
        ai = _invoke_with_retry(bound, messages, cfg)
        messages.append(ai)
        calls = list(getattr(ai, "tool_calls", None) or [])
        if not calls:
            break  # model stopped calling tools — try text coercion below
        for call in calls:
            name = call.get("name")
            args = call.get("args") or {}
            call_id = call.get("id") or name
            if name == "submit_result":
                try:
                    result = IngestionResult.model_validate(
                        {
                            "summary": args.get("summary", ""),
                            "new_pages": args.get("new_pages") or [],
                            "affected_pages": args.get("affected_pages") or [],
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    messages.append(
                        ToolMessage(
                            content=f"submit_result inválido: {exc}",
                            tool_call_id=call_id,
                            name=name,
                        )
                    )
                    continue
                messages.append(
                    ToolMessage(content="resultado registrado.", tool_call_id=call_id, name=name)
                )
                break
            fn = tools.get(name or "")
            if fn is None:
                out = f"tool desconhecida: {name}"
            else:
                if backend.on_event is not None:
                    try:
                        backend.on_event("tool_start", {"tool": name})
                    except Exception:  # noqa: BLE001 — telemetry never breaks the run
                        logger.debug("on_event failed", exc_info=True)
                try:
                    out = str(fn(**args))
                except Exception as exc:  # noqa: BLE001 — feed the error back
                    out = f"erro na tool {name}: {exc}"
            messages.append(ToolMessage(content=out, tool_call_id=call_id, name=name))
        if result is not None:
            break

    if result is None:
        result = _coerce_result(messages)
    if result is None:
        # Degraded fallback (#291 semantics): last text becomes the summary.
        used_fallback = True
        last_text = next(
            (
                m.content.strip()
                for m in reversed(messages)
                if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip()
            ),
            "",
        )
        result = IngestionResult(summary=last_text[:2000], new_pages=[], affected_pages=[])

    latency_ms = int((time.perf_counter() - start) * 1000)
    backend.execution_meta = extract_meta(
        {"messages": messages},
        model=str(getattr(model, "model", None) or cfg.model),
        latency_ms=latency_ms,
        used_fallback=used_fallback,
    )
    logger.info(
        "minimal run: tokens_in=%d tokens_out=%d tool_calls=%d latency=%dms fallback=%s",
        backend.execution_meta.tokens_in,
        backend.execution_meta.tokens_out,
        backend.execution_meta.tool_calls,
        latency_ms,
        used_fallback,
    )
    return result
