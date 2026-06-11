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
from importlib import resources
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..core.config import WorkspaceConfig
from .models import IngestionResult, LintReport, MaintenanceResult, QueryResult
from .telemetry import ExecutionMeta, extract_meta
from .tools import domain_tools, wiki_stats

if TYPE_CHECKING:
    from .backend import ChangeRequestBackend

logger = logging.getLogger("llmwiki.llm_agents.factory")


def _prompt(name: str) -> str:
    return (
        resources.files("llmwiki.llm_agents").joinpath("prompts", name).read_text(encoding="utf-8")
    )


def _build_model(cfg: WorkspaceConfig) -> Any:
    """Build the correct model object for the DeepAgent from the config.

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
    model_str = cfg.model
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
    from ..core.secrets import get_api_key  # noqa: PLC0415

    api_key = get_api_key(provider)
    pcfg = cfg.providers.get(provider)
    base_url = pcfg.base_url if pcfg else None
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


def _structured[T: BaseModel](state: dict[str, Any], schema: type[T]) -> T:
    """Extrai a resposta estruturada do estado retornado pelo agente.

    Se o agente não produzir structured_response (modelos fracos às vezes não
    chamam a tool final), cai para um resultado mínimo derivado da última
    mensagem, evitando quebrar o fluxo de change request já capturado no backend.
    """
    resp = state.get("structured_response")
    if isinstance(resp, schema):
        return resp
    if isinstance(resp, dict):
        return schema.model_validate(resp)
    # Fallback: tenta montar um resultado mínimo com o texto da última mensagem.
    last = ""
    for msg in reversed(state.get("messages", [])):
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            last = content.strip()
            break
    return _fallback(schema, last)


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


def _invoke_with_retry(agent: Any, message: str, cfg: WorkspaceConfig) -> dict[str, Any]:
    """Call ``agent.invoke`` with bounded retry+backoff on transient errors.

    A flaky provider call (network blip, 5xx) re-attempts instead of failing the
    whole job. ``JobCancelledError`` is never retried — cancellation is final.
    """
    from ..core.errors import JobCancelledError

    attempts = max(1, cfg.agent_max_retries)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            state: dict[str, Any] = agent.invoke(
                {"messages": [{"role": "user", "content": message}]}
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
) -> T:
    """Run the agent, time it, log structured-output fallback, capture telemetry.

    Telemetry is stashed on ``backend.execution_meta`` (when a backend is
    present) so services can persist it into the change request / job result.
    """
    start = time.perf_counter()
    state = _invoke_with_retry(agent, message, cfg)
    latency_ms = int((time.perf_counter() - start) * 1000)

    used_fallback = not _had_structured(state, schema)
    if used_fallback:
        logger.warning(
            "agent did not return structured_response for %s; using text fallback "
            "(model=%s, latency=%dms) — weak tool-calling model?",
            schema.__name__,
            cfg.model,
            latency_ms,
        )

    result = _structured(state, schema)
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


def _ingestion_message(
    cfg: WorkspaceConfig,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
) -> str:
    """Assemble the user message: today's date, wiki state, source + metadata.

    Dynamic context goes in the MESSAGE (not the static, cacheable system
    prompt) so the agent always sees the correct ``updated_at`` date, knows how
    big the wiki already is (#164), and gets the source's provenance (#163).
    """
    from ..core.misc import today

    return (
        f"DATA DE HOJE: {today()}\n"
        f"ESTADO DA WIKI: {wiki_stats(cfg.paths)}\n\n"
        f"FONTE: {source_path}\n"
        f"{_metadata_line(source_meta)}\n"
        f"--- TEXTO DA FONTE ---\n{source_text}\n--- FIM ---\n\n"
        "Integre esta fonte na wiki seguindo o protocolo."
    )


def run_ingestion(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
    source_meta: dict[str, str | None] | None = None,
) -> IngestionResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg),
        tools=domain_tools(cfg.paths),
        system_prompt=_prompt("ingestion.md"),
        backend=backend,
        middleware=_agent_middleware(backend),
        response_format=_response_format(IngestionResult),
    )
    message = _ingestion_message(
        cfg, source_path=source_path, source_text=source_text, source_meta=source_meta
    )
    return _invoke(agent, message, IngestionResult, cfg, backend)


def run_query(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None,
    *,
    question: str,
    save: bool,
) -> QueryResult:
    from deepagents import create_deep_agent

    kwargs: dict[str, Any] = {
        "model": _build_model(cfg),
        "tools": domain_tools(cfg.paths),
        "system_prompt": _prompt("query.md"),
        "middleware": _agent_middleware(backend),
        "response_format": _response_format(QueryResult),
    }
    if backend is not None:
        kwargs["backend"] = backend
    agent = create_deep_agent(**kwargs)
    suffix = " Gere também suggested_page para salvar a resposta." if save else ""
    return _invoke(agent, question + suffix, QueryResult, cfg, backend)


def run_lint(cfg: WorkspaceConfig) -> LintReport:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg),
        tools=domain_tools(cfg.paths),
        system_prompt=_prompt("lint.md"),
        middleware=_agent_middleware(None),
        response_format=_response_format(LintReport),
    )
    return _invoke(agent, "Audite a wiki e liste os problemas.", LintReport, cfg)


def run_maintenance(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    findings_text: str,
) -> MaintenanceResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg),
        tools=domain_tools(cfg.paths),
        system_prompt=_prompt("maintenance.md"),
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
