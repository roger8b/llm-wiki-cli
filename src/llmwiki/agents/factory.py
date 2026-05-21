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


def _build_model(model_str: str) -> Any:
    """Constrói o objeto de modelo correto para o DeepAgent.

    Modelos Ollama recebem ``disable_streaming=True`` + timeout generoso para
    evitar 502/unexpected-EOF em conexões cloud (ollama.com proxy não suporta
    respostas longas via SSE).  Outros provedores usam a string diretamente.
    """
    if not model_str.startswith("ollama:"):
        return model_str

    ollama_model = model_str[len("ollama:"):]  # ex: "gemma4:31b-cloud"
    try:
        from langchain_ollama import ChatOllama  # noqa: PLC0415
    except ImportError:
        return model_str  # fallback: deixa DeepAgents resolver

    return ChatOllama(
        model=ollama_model,
        disable_streaming=True,
        client_kwargs={"timeout": 300.0},
    )


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
    """Constrói um resultado mínimo quando não há structured_response."""
    summary = text[:500] or "(sem resumo do agente)"
    fields = schema.model_fields
    data: dict[str, Any] = {}
    if "summary" in fields:
        data["summary"] = summary
    if "answer" in fields:
        data["answer"] = summary
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
        model=_build_model(cfg.model),
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
        "model": _build_model(cfg.model),
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
        model=_build_model(cfg.model),
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
        model=_build_model(cfg.model),
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("maintenance.md"),
        backend=backend,
        response_format=_response_format(MaintenanceResult),
    )
    message = f"Problemas detectados:\n{findings_text}\n\nProponha correções."
    state = agent.invoke({"messages": [{"role": "user", "content": message}]})
    return _structured(state, MaintenanceResult)
