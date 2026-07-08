"""Query service: answers questions using the wiki as the primary source.

Read-only operation. If ``save=True`` and the agent suggests a page, it is
transformed into a change request (never written directly).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from pathlib import PurePosixPath

from ..core.config import WorkspaceConfig
from ..core.markdown import slugify
from ..core.models import ChangeRequest
from ..core.paths import BrainPaths
from ..db.repo import PageRepo
from ..llm_agents.backend import ChangeRequestBackend
from ..llm_agents.models import QueryResult
from .change_request_service import create_from_changes

logger = logging.getLogger("llmwiki.services.query")


def _validate_citations(
    result: QueryResult, paths: BrainPaths, conn: sqlite3.Connection
) -> int:
    """Mark citations that don't point at a real page/source as ``invalid``.

    Mutates ``result.citations`` in place. ``page`` resolves by exact indexed
    path or by title slug (same scheme as the lint resolver); a match normalises
    ``page`` to the canonical path. ``source`` must be an existing file under
    ``raw/`` (path traversal → invalid). Returns the number of invalid citations.
    """
    pages = PageRepo(conn).list()
    by_path = {p.path for p in pages}
    by_slug = {slugify(p.title): p.path for p in pages}
    for p in pages:
        by_slug.setdefault(slugify(PurePosixPath(p.path).stem), p.path)

    invalid = 0
    for cit in result.citations:
        ok = False
        if cit.page:
            target = cit.page.lstrip("/")
            if target in by_path:
                ok = True
            elif slugify(cit.page) in by_slug:
                cit.page = by_slug[slugify(cit.page)]  # normalise to canonical path
                ok = True
        if not ok and cit.source:
            ok = _raw_source_exists(cit.source, paths)
        cit.invalid = not ok
        if cit.invalid:
            invalid += 1
    if invalid:
        logger.warning(
            "ask(): %d/%d citações inválidas", invalid, len(result.citations)
        )
    return invalid


def _raw_source_exists(source: str, paths: BrainPaths) -> bool:
    """True if ``source`` is an existing file under ``raw/`` (no path traversal)."""
    norm = source.lstrip("/")
    if ".." in PurePosixPath(norm).parts:
        return False
    if not norm.startswith("raw/"):
        return False
    target = (paths.root / norm).resolve()
    if paths.root not in target.parents:
        return False
    return target.is_file()

# runner(cfg, backend, *, question, save) -> QueryResult
Runner = Callable[..., QueryResult]
# rag_runner(cfg, backend, *, question, context, save) -> QueryResult (#350)
RagRunner = Callable[..., QueryResult]

_ASK_MODES = ("agent", "rag", "auto")


def _default_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None,
    *,
    question: str,
    save: bool,
    on_token: Callable[[str], None] | None = None,
) -> QueryResult:
    from ..llm_agents.factory import run_query

    return run_query(cfg, backend, question=question, save=save, on_token=on_token)


def _default_rag_runner(
    cfg: WorkspaceConfig,
    backend: ChangeRequestBackend | None,
    *,
    question: str,
    context: str,
    save: bool,
    on_token: Callable[[str], None] | None = None,
) -> QueryResult:
    from ..llm_agents.factory import run_query_rag

    return run_query_rag(
        cfg, backend, question=question, context=context, save=save, on_token=on_token
    )


def _build_rag_context(
    question: str, paths: BrainPaths, conn: sqlite3.Connection, cfg: WorkspaceConfig
) -> tuple[list[str], str]:
    """Retrieve top-k pages for ``question`` and render the CONTEXTO block (#350).

    Retrieval happens IN CODE (no agent tool calls): one ``hybrid_search`` plus
    direct file reads, capped at ``cfg.ask_rag_max_context_chars``. Returns the
    page paths actually included and the rendered block ("" when no hits).
    """
    from ..search.factory import build_semantic_backend
    from ..search.service import hybrid_search

    embedder, store = build_semantic_backend(cfg, conn)
    hits = hybrid_search(
        conn, question, limit=max(1, cfg.ask_rag_top_k), embedder=embedder, store=store
    )
    cap = max(1000, cfg.ask_rag_max_context_chars)
    blocks: list[str] = []
    used: list[str] = []
    total = 0
    for hit in hits:
        target = paths.root / hit.path
        try:
            body = target.read_text(encoding="utf-8")
        except OSError:
            continue  # index drift: page vanished from disk — skip, don't break
        block = f"PÁGINA: {hit.path}\n{body}\n"
        if used and total + len(block) > cap:
            break
        if len(block) > cap:
            block = block[:cap]  # a single page bigger than the cap gets truncated
        blocks.append(block)
        used.append(hit.path)
        total += len(block)
    return used, "\n---\n".join(blocks)


def build_history_context(
    turns: list[tuple[str, str]], *, max_chars: int = 8000
) -> str:
    """Render prior conversation turns as a context preamble (#190).

    Returns an empty string when there are no turns. Each answer is truncated
    with "…" and the whole block is capped at ``max_chars`` (oldest turns dropped
    first so the most recent context survives).
    """
    if not turns:
        return ""
    per_answer = max(200, max_chars // max(1, len(turns)) - 80)
    lines: list[str] = []
    for i, (q, a) in enumerate(turns, 1):
        ans = a.strip().replace("\n", " ")
        if len(ans) > per_answer:
            ans = ans[:per_answer].rstrip() + "…"
        lines.append(f"[{i}] P: {q.strip()}\n    R (resumo): {ans}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        # Drop oldest turns until under the cap.
        while lines and len("\n".join(lines)) > max_chars:
            lines.pop(0)
        block = "\n".join(lines)
    return block


def ask(
    question: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    cfg: WorkspaceConfig,
    *,
    save: bool = False,
    runner: Runner | None = None,
    rag_runner: RagRunner | None = None,
    cancel_check: Callable[[], bool] | None = None,
    history_turns: list[tuple[str, str]] | None = None,
    on_token: Callable[[str], None] | None = None,
) -> tuple[QueryResult, ChangeRequest | None]:
    """Answers the question. If ``save`` and there is a suggested page, creates a CR.

    ``history_turns`` (prior conversation turns, oldest first) are folded into the
    message as user context — not as a source — so follow-up questions keep the
    thread without re-stating it. The agent still cites wiki pages only.

    ``on_token`` streams the answer tokens (#191) when the provider supports it.

    ``cfg.ask_mode`` selects the path (#350): ``"agent"`` (default) runs the
    legacy agent loop unchanged; ``"rag"`` retrieves top-k pages in code and
    makes one structured LLM call without tools; ``"auto"`` tries RAG and falls
    back to the agent path at most once (no hits or invalid citations). Unknown
    values degrade to ``"agent"``.
    """
    runner = runner or _default_runner
    rag_runner = rag_runner or _default_rag_runner
    # Backend always present: scopes read_file to brain root. ``ask`` is a
    # read-only operation, so the backend rejects writes and records any
    # attempt in ``write_attempts`` (audited below) instead of silently
    # dropping them.
    read_backend = ChangeRequestBackend(paths.root, read_only=True)
    read_backend.cancel_check = cancel_check
    context = build_history_context(
        history_turns or [], max_chars=cfg.ask_history_max_chars
    )
    agent_question = question
    if context:
        agent_question = (
            "CONVERSA ANTERIOR (contexto do usuário, NÃO é fonte — continue "
            "citando páginas da wiki):\n"
            f"{context}\n\nPERGUNTA ATUAL: {question}"
        )
    # Pass on_token only when set, so simple test runners need not accept it.
    extra = {"on_token": on_token} if on_token is not None else {}
    mode = cfg.ask_mode if cfg.ask_mode in _ASK_MODES else "agent"

    result: QueryResult | None = None
    if mode in ("rag", "auto"):
        hit_paths, rag_context = _build_rag_context(question, paths, conn, cfg)
        if hit_paths or mode == "rag":
            # "rag" answers even with no hits (explicit "no coverage" reply);
            # "auto" with 0 hits skips straight to the agent path.
            # In "auto" the RAG attempt may be discarded, so its tokens are
            # buffered and only flushed to the live stream if the answer
            # survives — otherwise the user would see the discarded answer
            # followed by the agent's one.
            rag_extra = dict(extra)
            buffered: list[str] = []
            if mode == "auto" and on_token is not None:
                rag_extra["on_token"] = buffered.append
            result = rag_runner(
                cfg,
                read_backend,
                question=agent_question,
                context=rag_context,
                save=save,
                **rag_extra,
            )
            # Citations validated per produced result (#172); in "auto", any
            # invalid citation discards the RAG answer and triggers the single
            # agent fallback below.
            invalid = _validate_citations(result, paths, conn)
            if mode == "auto" and invalid:
                logger.info(
                    "ask(): rag path had %d invalid citation(s); falling back to agent", invalid
                )
                result = None
            elif buffered and on_token is not None:
                for token in buffered:
                    on_token(token)

    if result is None:
        result = runner(cfg, read_backend, question=agent_question, save=save, **extra)
        # Resolve every citation against the index/raw so hallucinated
        # references are flagged (not removed — the user decides). #172
        _validate_citations(result, paths, conn)

    if read_backend.write_attempts:
        logger.warning(
            "ask(): agent attempted %d write(s) during a read-only query: %s",
            len(read_backend.write_attempts),
            ", ".join(sorted(set(read_backend.write_attempts))),
        )

    cr: ChangeRequest | None = None
    if save and result.suggested_page is not None:
        backend = ChangeRequestBackend(paths.root)
        backend.write(result.suggested_page.path, result.suggested_page.content)
        changes = backend.collect_changes()
        if changes:
            meta = read_backend.execution_meta
            cr = create_from_changes(
                changes,
                f"Saved answer: {question[:60]}",
                paths,
                conn,
                execution=meta.to_dict() if meta is not None else None,
            )
    return result, cr


def promote_answer(
    question: str,
    answer: str,
    paths: BrainPaths,
    conn: sqlite3.Connection,
    *,
    title: str | None = None,
) -> ChangeRequest | None:
    """Turn an already-generated answer into a wiki-page change request.

    No LLM call — the answer markdown is wrapped in a synthesis page and proposed
    as a change request (never written directly), mirroring the ``save`` flow.
    """
    from ..core.markdown import slugify
    from ..core.misc import today

    page_title = (title or question).strip() or "Untitled"
    slug = slugify(page_title)
    path = f"wiki/synthesis/{slug}.md"
    content = (
        "---\n"
        f"title: {page_title}\n"
        "type: synthesis\n"
        "tags: []\n"
        "sources: []\n"
        f"updated_at: {today()}\n"
        "confidence: medium\n"
        "---\n"
        f"# {page_title}\n\n"
        f"{answer.strip()}\n"
    )

    backend = ChangeRequestBackend(paths.root)
    backend.write(path, content)
    changes = backend.collect_changes()
    if not changes:
        return None
    return create_from_changes(
        changes,
        f"Promoted answer: {question[:60]}",
        paths,
        conn,
    )
