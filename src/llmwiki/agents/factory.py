"""Construção e execução dos agentes DeepAgents.

Cada ``run_*`` monta um agente, executa via ``invoke`` e extrai a resposta
estruturada (``structured_response``). O conteúdo das páginas é capturado pelo
``backend`` (ChangeRequestBackend) — não vem na resposta.

Importa DeepAgents de forma preguiçosa para que o core/CLI funcione sem o extra
``agent`` instalado, até que uma operação de LLM seja efetivamente requisitada.
"""

from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..core.config import WorkspaceConfig
from .models import IngestionResult, LintReport, MaintenanceResult, QueryResult
from .tools import make_search_pages

if TYPE_CHECKING:
    from .backend import ChangeRequestBackend


def _prompt(name: str) -> str:
    return (
        resources.files("llmwiki.agents").joinpath("prompts", name).read_text(encoding="utf-8")
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


def run_ingestion(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
) -> IngestionResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg),
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("ingestion.md"),
        backend=backend,
        response_format=_response_format(IngestionResult),
    )
    message = (
        f"FONTE: {source_path}\n\n"
        f"--- TEXTO DA FONTE ---\n{source_text}\n--- FIM ---\n\n"
        "Integre esta fonte na wiki seguindo o protocolo."
    )
    state = agent.invoke({"messages": [{"role": "user", "content": message}]})
    return _structured(state, IngestionResult)


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
        "tools": [make_search_pages(cfg.paths)],
        "system_prompt": _prompt("query.md"),
        "response_format": _response_format(QueryResult),
    }
    if backend is not None:
        kwargs["backend"] = backend
    agent = create_deep_agent(**kwargs)
    suffix = " Gere também suggested_page para salvar a resposta." if save else ""
    state = agent.invoke(
        {"messages": [{"role": "user", "content": question + suffix}]}
    )
    return _structured(state, QueryResult)


def run_lint(cfg: WorkspaceConfig) -> LintReport:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg),
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("lint.md"),
        response_format=_response_format(LintReport),
    )
    state = agent.invoke(
        {"messages": [{"role": "user", "content": "Audite a wiki e liste os problemas."}]}
    )
    return _structured(state, LintReport)


def run_maintenance(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    findings_text: str,
) -> MaintenanceResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=_build_model(cfg),
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("maintenance.md"),
        backend=backend,
        response_format=_response_format(MaintenanceResult),
    )
    message = f"Problemas detectados:\n{findings_text}\n\nProponha correções."
    state = agent.invoke({"messages": [{"role": "user", "content": message}]})
    return _structured(state, MaintenanceResult)
