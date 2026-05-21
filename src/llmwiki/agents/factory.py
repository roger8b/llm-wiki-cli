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


def _structured[T: BaseModel](state: dict[str, Any], schema: type[T]) -> T:
    """Extrai a resposta estruturada do estado retornado pelo agente."""
    resp = state.get("structured_response")
    if resp is None:
        raise RuntimeError("Agente não devolveu structured_response.")
    if isinstance(resp, schema):
        return resp
    return schema.model_validate(resp)


def run_ingestion(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend,
    *,
    source_path: str,
    source_text: str,
) -> IngestionResult:
    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=cfg.model,
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("ingestion.md"),
        backend=backend,
        response_format=IngestionResult,
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
        "model": cfg.model,
        "tools": [make_search_pages(cfg.paths)],
        "system_prompt": _prompt("query.md"),
        "response_format": QueryResult,
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
        model=cfg.model,
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("lint.md"),
        response_format=LintReport,
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
        model=cfg.model,
        tools=[make_search_pages(cfg.paths)],
        system_prompt=_prompt("maintenance.md"),
        backend=backend,
        response_format=MaintenanceResult,
    )
    message = f"Problemas detectados:\n{findings_text}\n\nProponha correções."
    state = agent.invoke({"messages": [{"role": "user", "content": message}]})
    return _structured(state, MaintenanceResult)
