"""Construção e execução dos agentes DeepAgents.

Cada ``run_*`` monta um agente, executa via ``invoke`` e extrai a resposta
estruturada (``structured_response``). O conteúdo das páginas é capturado pelo
``backend`` (ChangeRequestBackend) — não vem na resposta.

Importa DeepAgents de forma preguiçosa para que o core/CLI funcione sem o extra
``agent`` instalado, até que uma operação de LLM seja efetivamente requisitada.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from importlib import resources
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..core.config import WorkspaceConfig
from .models import (
    IngestionResult,
    LintReport,
    MaintenanceResult,
    OutlinePlan,
    QueryResult,
)
from .telemetry import ExecutionMeta, extract_meta
from .tools import domain_tools, wiki_stats

if TYPE_CHECKING:
    from .backend import ChangeRequestBackend

logger = logging.getLogger("llmwiki.llm_agents.factory")


def _prompt(name: str) -> str:
    return (
        resources.files("llmwiki.llm_agents").joinpath("prompts", name).read_text(encoding="utf-8")
    )


# Providers whose chat models honour an Anthropic-style ``cache_control`` marker
# on the (static, identical-every-pass) system prompt. MiniMax-M3 is served over
# the Anthropic-compatible endpoint, so it rides this path too.
_PROMPT_CACHE_PROVIDERS = {"anthropic"}


def _supports_prompt_cache(cfg: WorkspaceConfig) -> bool:
    return cfg.model.partition(":")[0] in _PROMPT_CACHE_PROVIDERS


def _cached_prompt(name: str, cfg: WorkspaceConfig) -> Any:
    """Return the system prompt, marked cacheable on compatible providers (#278).

    The system prompt is static and resent on every ingestion pass. On Anthropic
    (and the Anthropic-compatible MiniMax endpoint) we wrap it in a
    ``cache_control`` content block so the provider caches it across passes and
    bills the system prompt at the cheaper cache-read rate. Other providers
    (e.g. local Ollama) get the plain string — no behavioural change. OpenAI
    caches automatically and needs no marker.
    """
    text = _prompt(name)
    if not _supports_prompt_cache(cfg):
        return text
    from langchain_core.messages import SystemMessage  # noqa: PLC0415

    return SystemMessage(
        content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    )


# Fallback chains for per-operation model resolution (#279, #293). An operation
# resolves to the first override present in its chain, else the global model.
# "outline" only plans concepts (lighter work), so it can run a cheaper model
# than the ingest writer — falling back to the ingest override, then the global.
_MODEL_CHAINS: dict[str, tuple[str, ...]] = {
    "outline": ("outline", "ingest"),
}


def resolve_model(cfg: WorkspaceConfig, operation: str | None = None) -> str:
    """Effective model string for an operation (#279, #293).

    ``operation`` is one of ``"ingest"``, ``"ask"``, ``"maintain"``, ``"outline"``.
    When ``cfg.models`` has an override for it, that wins; ``"outline"`` falls
    back to the ``"ingest"`` override before the global ``cfg.model`` so a strong
    ingest model still covers the outline unless a lighter one is pinned. ``None``
    always resolves to ``cfg.model``.
    """
    if operation:
        for key in _MODEL_CHAINS.get(operation, (operation,)):
            override = cfg.models.get(key)
            if override:
                return override
    return cfg.model


def _build_model(cfg: WorkspaceConfig, operation: str | None = None) -> Any:
    """Build the correct model object for the DeepAgent from the config.

    The effective model is resolved per ``operation`` (#279): an ingestion pass
    can run a stronger model than ``ask`` via ``cfg.models``. Falls back to the
    global ``cfg.model`` when no override applies.

    Ollama models (local or cloud) are returned as a ChatOllama instance that
    forces ``stream=False`` at the HTTP level.  The langchain_ollama default is
    ``stream=True`` which streams over SSE; cloud Ollama proxies (ollama.com)
    drop long streaming connections with 502/EOF.  We override ``_chat_params``
    to always set ``stream=False`` so the proxy returns the full response in
    one JSON blob.

    Tuning params (``num_ctx``, ``temperature``, ``request_timeout``) come from
    the workspace config and apply to Ollama models. Other providers are
    returned as the model string (DeepAgents resolves them).
    """
    model_str = resolve_model(cfg, operation)
    provider, _, name = model_str.partition(":")

    if provider != "ollama":
        built = _build_remote(provider, name, cfg)
        return built if built is not None else model_str

    ollama_model = model_str[len("ollama:"):]  # e.g. "gemma4:31b-cloud"
    try:
        from langchain_ollama import ChatOllama  # noqa: PLC0415
    except ImportError:
        return model_str  # fallback: let DeepAgents resolve

    # NOTE: mypy strict requires the langchain extras (`ollama`, `openai`, ...)
    # to be installed; without them ChatOllama is `Any` and these declarations
    # would trip `[misc]` / `[override]` errors. CI lint job installs all extras.
    class _NoStreamOllama(ChatOllama):
        """ChatOllama subclass that always uses stream=False in HTTP requests."""

        def _chat_params(self, messages: Any, stop: Any = None, **kwargs: Any) -> Any:
            params = super()._chat_params(messages, stop, **kwargs)
            params["stream"] = False
            return params

    kwargs: dict[str, Any] = {
        "model": ollama_model,
        # Ollama defaults num_ctx to 2048, which is too small once the agent
        # reads wiki pages into context — answers get squeezed/truncated.
        "num_ctx": cfg.num_ctx,
        "client_kwargs": {"timeout": float(cfg.request_timeout)},
    }
    if cfg.temperature is not None:
        kwargs["temperature"] = cfg.temperature
    return _NoStreamOllama(**kwargs)


def _build_remote(provider: str, name: str, cfg: WorkspaceConfig) -> Any:
    """Build a hosted provider chat model with key (keychain) + base_url.

    Returns None to signal "let DeepAgents resolve the string" when the
    provider package isn't installed.
    """
    from ..core.errors import ProviderError  # noqa: PLC0415
    from ..core.secrets import get_api_key  # noqa: PLC0415

    api_key = get_api_key(provider)
    pcfg = cfg.providers.get(provider)
    base_url = pcfg.base_url if pcfg else None
    # A hosted provider with no key and no custom base_url cannot authenticate.
    # Fail fast with a clear, typed error (CLI maps it to exit 5) instead of an
    # opaque 401 deep inside the agent run. A base_url may point at a local proxy
    # that needs no key, so only guard when neither is present.
    if provider in {"anthropic", "openai", "google"} and not api_key and not base_url:
        raise ProviderError(
            f"No API key configured for provider '{provider}'. "
            f"Set the {provider.upper()}_API_KEY environment variable "
            "(or configure a base_url for a local endpoint)."
        )
    common: dict[str, Any] = {"model": name}
    if cfg.temperature is not None:
        common["temperature"] = cfg.temperature

    try:
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic  # noqa: PLC0415

            kw = dict(common, timeout=float(cfg.request_timeout))
            if api_key:
                kw["api_key"] = api_key
            if base_url:
                kw["base_url"] = base_url
            return ChatAnthropic(**kw)
        if provider == "openai":
            from langchain_openai import ChatOpenAI  # noqa: PLC0415

            kw = dict(common, timeout=float(cfg.request_timeout))
            if api_key:
                kw["api_key"] = api_key
            if base_url:
                kw["base_url"] = base_url
            return ChatOpenAI(**kw)
        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

            kw = dict(common)
            if api_key:
                kw["google_api_key"] = api_key
            return ChatGoogleGenerativeAI(**kw)
    except ImportError:
        return None
    return None


def _response_format(schema: type[BaseModel]) -> Any:
    """Força structured output via tool call (ToolStrategy).

    Mais robusto que a estratégia nativa: muitos modelos servidos via Ollama não
    cumprem JSON schema nativo, mas suportam tool calling. ``handle_errors`` deixa
    o agente reparar saídas malformadas em vez de quebrar a execução.
    """
    from langchain.agents.structured_output import ToolStrategy

    return ToolStrategy(schema, handle_errors=True)


def _coerce_from_messages[T: BaseModel](
    state: dict[str, Any], schema: type[T]
) -> T | None:
    """Recover a result a weak model emitted as JSON *text* instead of via the
    structured-output tool (#291).

    Some tool-calling-weak models (incl. MiniMax/GPT-mini under load) answer with
    the schema's JSON in the final message rather than calling the final
    structured-output tool. That used to count as a fallback and throw the
    structured data away. Here we parse the last messages — including a
    ```json ...``` fence — and validate into ``schema``. Pure parsing of the
    state we already have: **no model re-invoke**. Returns ``None`` when nothing
    parses cleanly, so the caller uses the minimal fallback.
    """
    import json  # noqa: PLC0415
    import re  # noqa: PLC0415

    for msg in reversed(state.get("messages", [])):
        content = getattr(msg, "content", None)
        if not isinstance(content, str) or not content.strip():
            continue
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            continue
        try:
            data = json.loads(match.group(0))
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            return schema.model_validate(data)
        except Exception:  # noqa: BLE001 — not this message; keep scanning
            continue
    return None


def _resolve_structured[T: BaseModel](
    state: dict[str, Any], schema: type[T]
) -> tuple[T, bool]:
    """Return ``(result, used_minimal_fallback)``.

    Order: structured_response → JSON-in-text coercion (#291) → minimal fallback
    from the last message. ``used_minimal_fallback`` is True ONLY when we had to
    synthesize a degraded result — coerced JSON does NOT count, so the fallback
    metric reflects real data loss, not a model that merely chose text output.
    """
    resp = state.get("structured_response")
    if isinstance(resp, schema):
        return resp, False
    if isinstance(resp, dict):
        return schema.model_validate(resp), False
    coerced = _coerce_from_messages(state, schema)
    if coerced is not None:
        return coerced, False
    last = ""
    for msg in reversed(state.get("messages", [])):
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            last = content.strip()
            break
    return _fallback(schema, last), True


def _structured[T: BaseModel](state: dict[str, Any], schema: type[T]) -> T:
    """Extrai a resposta estruturada do estado retornado pelo agente.

    Se o agente não produzir structured_response (modelos fracos às vezes não
    chamam a tool final), tenta coagir JSON da última mensagem (#291) e só então
    cai para um resultado mínimo, evitando quebrar o fluxo de change request já
    capturado no backend.
    """
    return _resolve_structured(state, schema)[0]


def _fallback[T: BaseModel](schema: type[T], text: str) -> T:
    """Constrói um resultado mínimo quando não há structured_response.

    Usa o texto completo da última mensagem do agente — nunca trunca a
    ``answer`` (a resposta para o usuário). ``summary`` recebe um recorte
    generoso apenas para não inflar cards de CR.
    """
    text = text or "(sem resposta do agente)"
    fields = schema.model_fields
    data: dict[str, Any] = {}
    if "summary" in fields:
        # generous cap — only to keep CR summaries from being enormous
        data["summary"] = text[:2000]
    if "answer" in fields:
        data["answer"] = text  # full answer, never truncated
    try:
        return schema.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Agente não devolveu structured_response e fallback falhou: {exc}"
        ) from exc


def _had_structured(state: dict[str, Any], schema: type[BaseModel]) -> bool:
    resp = state.get("structured_response")
    return isinstance(resp, schema | dict)


def _agent_middleware(backend: ChangeRequestBackend | None) -> list[Any]:
    """Middleware stack: always hide ``execute``; add cancellation if requested."""
    from .middleware import CancellationMiddleware, ExcludeToolsMiddleware

    mw: list[Any] = [ExcludeToolsMiddleware()]
    if backend is not None and backend.cancel_check is not None:
        mw.append(CancellationMiddleware(backend.cancel_check))
    return mw


def _invoke_with_retry(
    agent: Any,
    message: str,
    cfg: WorkspaceConfig,
    on_token: Callable[[str], None] | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    max_retries: int | None = None,
) -> dict[str, Any]:
    """Call ``agent.invoke`` with bounded retry+backoff on transient errors.

    A flaky provider call (network blip, 5xx) re-attempts instead of failing the
    whole job. ``JobCancelledError`` is never retried — cancellation is final.
    When ``on_token`` is set, a streaming callback forwards the model's answer
    tokens (#191); providers that don't stream simply never fire it. When
    ``on_event`` is set, tool calls are forwarded as live progress events (#272).
    """
    from ..core.errors import JobCancelledError

    # Only build a callbacks config when streaming/eventing, and only pass it
    # when set — keeps the call compatible with agents/fakes whose invoke()
    # takes no config.
    callbacks: list[Any] = []
    if on_token is not None:
        from .streaming import make_token_handler  # noqa: PLC0415

        callbacks.append(make_token_handler(on_token))
    if on_event is not None:
        from .streaming import make_ingestion_event_handler  # noqa: PLC0415

        callbacks.append(make_ingestion_event_handler(on_event))
    extra: dict[str, Any] = {}
    if callbacks:
        extra["config"] = {"callbacks": callbacks}

    attempts = max(1, max_retries if max_retries is not None else cfg.agent_max_retries)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            state: dict[str, Any] = agent.invoke(
                {"messages": [{"role": "user", "content": message}]},
                **extra,
            )
            return state
        except JobCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts:
                break
            backoff = min(2.0 ** (attempt - 1), 8.0)
            logger.warning(
                "agent.invoke failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                attempts,
                exc,
                backoff,
            )
            time.sleep(backoff)
    assert last_exc is not None
    raise last_exc


def _invoke[T: BaseModel](
    agent: Any,
    message: str,
    schema: type[T],
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None = None,
    on_token: Callable[[str], None] | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    max_retries: int | None = None,
) -> T:
    """Run the agent, time it, log structured-output fallback, capture telemetry.

    Telemetry is stashed on ``backend.execution_meta`` (when a backend is
    present) so services can persist it into the change request / job result.
    ``on_token`` enables answer token streaming (#191); ``on_event`` enables
    live tool-call progress events (#272). ``max_retries`` overrides
    ``cfg.agent_max_retries`` for this call (ingestion uses ``ingest_max_retries``
    so it can cap retries without affecting ``ask``, #291).
    """
    start = time.perf_counter()
    state = _invoke_with_retry(
        agent, message, cfg, on_token, on_event, max_retries=max_retries
    )
    latency_ms = int((time.perf_counter() - start) * 1000)

    # used_fallback is True only when even JSON-in-text coercion failed (#291) —
    # so the metric reflects real data loss, not a model that answered as text.
    result, used_fallback = _resolve_structured(state, schema)
    if used_fallback:
        logger.warning(
            "agent did not return a coercible structured result for %s; using text "
            "fallback (model=%s, latency=%dms) — weak tool-calling model?",
            schema.__name__,
            cfg.model,
            latency_ms,
        )

    meta: ExecutionMeta = extract_meta(
        state, model=cfg.model, latency_ms=latency_ms, used_fallback=used_fallback
    )
    logger.info(
        "agent run %s: model=%s tokens_in=%d tokens_out=%d tool_calls=%d latency=%dms fallback=%s",
        schema.__name__,
        meta.model,
        meta.tokens_in,
        meta.tokens_out,
        meta.tool_calls,
        meta.latency_ms,
        meta.used_fallback,
    )
    if backend is not None:
        backend.execution_meta = meta
    return result


def _metadata_line(source_meta: dict[str, str | None] | None) -> str:
    """Render a ``METADADOS:`` line with only the present provenance fields."""
    if not source_meta:
        return ""
    labels = {"title": "título", "author": "autor", "date": "data", "url": "url"}
    parts = [
        f"{labels[k]}={v}"
        for k, v in source_meta.items()
        if k in labels and v
    ]
    return f"METADADOS: {', '.join(parts)}\n" if parts else ""


# Pre-fetched outline candidates, memoized by DB file signature within a run
# (#292). The committed DB doesn't change mid-run (staged pages live in the CR
# overlay), so each concept's hybrid search runs once even across chunk passes;
# the signature key auto-invalidates the moment a CR is applied + reindexed.
_prefetch_cache: dict[str, tuple[tuple[int, int], list[dict[str, object]]]] = {}


def reset_prefetch_cache() -> None:
    """Drop the memoized prefetch entries (used by tests for isolation)."""
    _prefetch_cache.clear()


def prefetch_candidates(
    cfg: WorkspaceConfig, concepts: list[str], *, limit: int
) -> dict[str, list[dict[str, object]]]:
    """Map each outline concept → its top existing wiki pages (#292).

    Runs one hybrid search per concept IN CODE — no LLM, no agent tool call — so
    the chunk passes can decide edit-vs-create straight from the message instead
    of spending sequential ``search_pages``/``related_pages`` round-trips. Reuses
    a single connection + semantic backend for the whole batch and memoizes by DB
    signature, so repeated chunks in a run don't re-search. Returns ``{}`` when
    disabled (``limit <= 0``), there are no concepts, or there's no DB yet (empty
    wiki — nothing to find).
    """
    if limit <= 0 or not concepts:
        return {}
    paths = cfg.paths
    try:
        st = paths.db_path.stat()
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}  # no DB file yet — empty wiki

    import sqlite3  # noqa: PLC0415

    from ..db.connection import get_connection  # noqa: PLC0415
    from ..search.factory import build_semantic_backend  # noqa: PLC0415
    from ..search.service import hybrid_search  # noqa: PLC0415

    out: dict[str, list[dict[str, object]]] = {}
    conn = get_connection(paths.db_path)
    try:
        assert isinstance(conn, sqlite3.Connection)
        embedder, store = build_semantic_backend(cfg, conn)
        for concept in concepts:
            key = f"{paths.db_path}|{limit}|{concept}"
            cached = _prefetch_cache.get(key)
            if cached is not None and cached[0] == sig:
                out[concept] = cached[1]
                continue
            hits = hybrid_search(conn, concept, limit=limit, embedder=embedder, store=store)
            cands: list[dict[str, object]] = [
                {"path": h.path, "title": h.title, "score": round(h.score, 3)}
                for h in hits
            ]
            _prefetch_cache[key] = (sig, cands)
            out[concept] = cands
    finally:
        conn.close()
    return out


def _candidates_block(candidates: dict[str, list[dict[str, object]]] | None) -> str:
    """Render the pre-fetched related-pages block for the chunk message (#292)."""
    if not candidates:
        return ""
    lines = [
        "PÁGINAS EXISTENTES RELACIONADAS (pré-buscadas — PREFIRA edit_file numa "
        "delas a criar duplicata; só crie nova se for um conceito realmente "
        "distinto):"
    ]
    for concept, cands in candidates.items():
        if not cands:
            continue
        rendered = "; ".join(f"{c['path']} — {c['title']}" for c in cands)
        lines.append(f"- {concept}: {rendered}")
    if len(lines) == 1:  # every concept had zero hits — no block at all
        return ""
    return "\n".join(lines)


def _chunk_context(
    outline: OutlinePlan | None,
    part: tuple[int, int] | None,
    candidates: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    """Render the multi-pass preamble (outline + part-i-of-n note), or ''.

    The wording is part-aware: part 1 must CREATE the pages for its concepts
    (nothing exists yet); later parts may find pages from earlier parts and
    should update/extend them, but still create pages for new concepts. The old
    one-size note ("pages already exist — update instead of create") was
    contradictory on part 1 and could make the agent write nothing.
    """
    if part is None:
        return ""
    i, n = part
    if i == 1:
        note = (
            f"PARTE 1 DE {n} DA MESMA FONTE (dividida por ser longa). NADA foi "
            "escrito ainda — CRIE (write_file) as páginas dos conceitos desta "
            "parte normalmente. As próximas partes continuam a MESMA fonte."
        )
    else:
        note = (
            f"PARTE {i} DE {n} DA MESMA FONTE. As partes anteriores podem já ter "
            "criado páginas — use search_pages/related_pages para encontrá-las e "
            "ATUALIZE/estenda (edit_file) em vez de duplicar. Para conceitos ainda "
            "NÃO cobertos, CRIE a página (write_file)."
        )
    lines = [note]
    if outline is not None and (outline.concepts or outline.summary):
        if outline.summary:
            lines.append(f"RESUMO DA FONTE: {outline.summary}")
        if outline.concepts:
            lines.append("CONCEITOS ESPERADOS (plano global): " + "; ".join(outline.concepts))
    block = _candidates_block(candidates)
    if block:
        lines.append(block)
    return "\n".join(lines) + "\n\n"


def _ingestion_message(
    cfg: WorkspaceConfig,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
    outline: OutlinePlan | None = None,
    part: tuple[int, int] | None = None,
    candidates: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    """Assemble the user message: today's date, wiki state, source + metadata.

    Dynamic context goes in the MESSAGE (not the static, cacheable system
    prompt) so the agent always sees the correct ``updated_at`` date, knows how
    big the wiki already is (#164), and gets the source's provenance (#163).
    For long sources the message also carries the global outline and a
    "part i of n" note so chunk passes stay consistent (#162), plus the
    pre-fetched related pages per concept (#292).
    """
    from ..core.misc import today

    return (
        f"DATA DE HOJE: {today()}\n"
        f"ESTADO DA WIKI: {wiki_stats(cfg.paths)}\n\n"
        f"{_chunk_context(outline, part, candidates)}"
        f"FONTE: {source_path}\n"
        f"{_metadata_line(source_meta)}\n"
        f"--- TEXTO DA FONTE ---\n{source_text}\n--- FIM ---\n\n"
        "Integre esta fonte na wiki seguindo o protocolo."
    )


def _fix_message(findings: list[str]) -> str:
    """Correction prompt for the self-correction loop (#166)."""
    listed = "\n".join(f"- {f}" for f in findings)
    return (
        "As páginas que você escreveu têm problemas estruturais:\n"
        f"{listed}\n\n"
        "Corrija-as usando edit_file/write_file no MESMO path. "
        "NÃO crie páginas novas e não mude nenhuma página correta. "
        "Retorne o resultado estruturado ao terminar."
    )


def run_ingestion(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
    outline: OutlinePlan | None = None,
    part: tuple[int, int] | None = None,
    fix_findings: list[str] | None = None,
) -> IngestionResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg, "ingest"),
        tools=domain_tools(cfg.paths, cfg),
        system_prompt=_cached_prompt("ingestion.md", cfg),
        backend=backend,
        middleware=_agent_middleware(backend),
        response_format=_response_format(IngestionResult),
    )
    if fix_findings:
        message = _fix_message(fix_findings)
    else:
        # Pre-fetch existing pages for the outline's concepts (#292) so the agent
        # decides edit-vs-create from the message instead of via tool round-trips.
        candidates = (
            prefetch_candidates(
                cfg, outline.concepts, limit=cfg.ingest_prefetch_candidates
            )
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
        )
    # Route the agent's tool calls through the same live-event sink the backend
    # uses for page writes (#272), so the job timeline sees both.
    return _invoke(
        agent, message, IngestionResult, cfg, backend,
        on_event=backend.on_event, max_retries=cfg.ingest_max_retries,
    )


def _outline_message(
    cfg: WorkspaceConfig,
    *,
    source_meta: dict[str, str | None] | None,
    chunk_summaries: list[str],
) -> str:
    """User message for the outline pass: only the opening of each chunk."""
    parts = [
        f"FONTE longa dividida em {len(chunk_summaries)} partes.",
        _metadata_line(source_meta).rstrip("\n"),
    ]
    for i, summary in enumerate(chunk_summaries, start=1):
        parts.append(f"\n--- INÍCIO DA PARTE {i} ---\n{summary}")
    parts.append("\nListe os conceitos esperados de toda a fonte e um resumo.")
    return "\n".join(p for p in parts if p)


def run_outline(
    cfg: WorkspaceConfig,
    *,
    source_meta: dict[str, str | None] | None = None,
    chunk_summaries: list[str],
) -> OutlinePlan:
    """Plan the concepts of a long source before chunk passes (#162).

    Read-only: built with a ``read_only`` backend so no write tool can stage a
    page during planning.
    """
    from deepagents import create_deep_agent

    from .backend import ChangeRequestBackend

    backend = ChangeRequestBackend(cfg.brain_root, read_only=True)
    agent = create_deep_agent(
        model=_build_model(cfg, "outline"),
        tools=domain_tools(cfg.paths, cfg),
        system_prompt=_cached_prompt("outline.md", cfg),
        backend=backend,
        middleware=_agent_middleware(backend),
        response_format=_response_format(OutlinePlan),
    )
    message = _outline_message(
        cfg, source_meta=source_meta, chunk_summaries=chunk_summaries
    )
    return _invoke(
        agent, message, OutlinePlan, cfg, backend, max_retries=cfg.ingest_max_retries
    )


def run_query(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None,
    *,
    question: str,
    save: bool,
    on_token: Callable[[str], None] | None = None,
) -> QueryResult:
    from deepagents import create_deep_agent

    kwargs: dict[str, Any] = {
        "model": _build_model(cfg, "ask"),
        "tools": domain_tools(cfg.paths, cfg),
        "system_prompt": _cached_prompt("query.md", cfg),
        "middleware": _agent_middleware(backend),
        "response_format": _response_format(QueryResult),
    }
    if backend is not None:
        kwargs["backend"] = backend
    agent = create_deep_agent(**kwargs)
    suffix = " Gere também suggested_page para salvar a resposta." if save else ""
    return _invoke(agent, question + suffix, QueryResult, cfg, backend, on_token=on_token)


def run_lint(
    cfg: WorkspaceConfig,
    *,
    pages: list[str] | None = None,
    scope_name: str | None = None,
) -> LintReport:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg, "maintain"),
        tools=domain_tools(cfg.paths, cfg),
        system_prompt=_cached_prompt("lint.md", cfg),
        middleware=_agent_middleware(None),
        response_format=_response_format(LintReport),
    )
    if pages:
        scope = f" (lote: {scope_name})" if scope_name else ""
        listing = "\n".join(f"- {p}" for p in pages)
        message = (
            f"Audite EXATAMENTE estas páginas{scope} (leia cada uma com read_file):\n"
            f"{listing}\n\n"
            "Foque em problemas internos ao lote e contradições com páginas que "
            "você consultar via search_pages. Não invente problemas."
        )
    else:
        message = "Audite a wiki e liste os problemas."
    return _invoke(agent, message, LintReport, cfg)


def run_maintenance(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    findings_text: str,
) -> MaintenanceResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg, "maintain"),
        tools=domain_tools(cfg.paths, cfg),
        system_prompt=_cached_prompt("maintenance.md", cfg),
        backend=backend,
        middleware=_agent_middleware(backend),
        response_format=_response_format(MaintenanceResult),
    )
    from ..core.misc import today

    message = (
        f"DATA DE HOJE: {today()}\n\n"
        f"Problemas detectados:\n{findings_text}\n\nProponha correções."
    )
    return _invoke(agent, message, MaintenanceResult, cfg, backend)
