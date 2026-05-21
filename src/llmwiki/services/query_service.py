"""Query service: responde perguntas usando a wiki como fonte primária.

Operação somente leitura. Se ``save=True`` e o agente sugerir uma página, ela é
transformada em change request (nunca escrita direto).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ..agents.backend import ChangeRequestBackend
from ..agents.models import QueryResult
from ..core.config import WorkspaceConfig
from ..core.models import ChangeRequest
from ..core.paths import BrainPaths
from .change_request_service import create_from_changes

# runner(cfg, backend, *, question, save) -> QueryResult
Runner = Callable[..., QueryResult]


def _default_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None,
    *,
    question: str,
    save: bool,
) -> QueryResult:
    from ..agents.factory import run_query

    return run_query(cfg, backend, question=question, save=save)


def ask(
    question: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    save: bool = False,
    runner: Runner | None = None,
) -> tuple[QueryResult, ChangeRequest | None]:
    """Responde a pergunta. Se ``save`` e houver página sugerida, cria um CR."""
    runner = runner or _default_runner
    # Backend sempre presente: scopa read_file ao brain root.
    # Writes do agente ficam no staging e são descartados (operação read-only).
    read_backend = ChangeRequestBackend(paths.root)
    result = runner(cfg, read_backend, question=question, save=save)

    cr: ChangeRequest | None = None
    if save and result.suggested_page is not None:
        backend = ChangeRequestBackend(paths.root)
        backend.write(result.suggested_page.path, result.suggested_page.content)
        changes = backend.collect_changes()
        if changes:
            cr = create_from_changes(
                changes,
                f"Resposta salva: {question[:60]}",
                paths,
                conn,
            )
    return result, cr
