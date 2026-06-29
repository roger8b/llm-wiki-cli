"""Standardised CLI exit codes and error rendering (#198).

A single place maps typed domain exceptions to stable exit codes and slugs so
external agents can branch on failure category without parsing free text. The
central handler lives in :mod:`llmwiki.interfaces.cli.main`.

| code | meaning            | examples                                        |
|------|--------------------|-------------------------------------------------|
| 0    | success            |                                                 |
| 1    | unexpected error   | unmapped exception                              |
| 2    | invalid usage      | bad flag/arg (Typer)                            |
| 3    | not found          | CR/page/source/brain missing                    |
| 4    | conflict/duplicate | SourceAlreadyProcessedError, colliding slug     |
| 5    | provider/LLM       | missing API key, model timeout                  |
| 6    | extraction         | ExtractorUnavailableError, EmptyExtractionError |
| 130  | cancelled          | JobCancelledError / Ctrl-C                       |
"""

from __future__ import annotations

import functools
import json
import os
import sys
from collections.abc import Callable

import typer

from ...core.errors import (
    BrainExistsError,
    BrainNotFoundError,
    EmptyExtractionError,
    ExtractorUnavailableError,
    JobCancelledError,
    NotFoundError,
    PageExistsError,
    PathOutsideBrainError,
    ProviderError,
    SourceAlreadyIngestedError,
    SourceAlreadyProcessedError,
    WikiError,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_CONFLICT = 4
EXIT_PROVIDER = 5
EXIT_EXTRACTION = 6
EXIT_CANCELLED = 130

# Most specific first. (exception type) -> (exit code, stable slug).
_MAP: list[tuple[type[BaseException], tuple[int, str]]] = [
    (SourceAlreadyIngestedError, (EXIT_CONFLICT, "source_already_ingested")),
    (SourceAlreadyProcessedError, (EXIT_CONFLICT, "source_already_processed")),
    (PageExistsError, (EXIT_CONFLICT, "page_exists")),
    (BrainExistsError, (EXIT_CONFLICT, "brain_exists")),
    (BrainNotFoundError, (EXIT_NOT_FOUND, "brain_not_found")),
    (NotFoundError, (EXIT_NOT_FOUND, "not_found")),
    (PathOutsideBrainError, (EXIT_USAGE, "path_outside_brain")),
    (ExtractorUnavailableError, (EXIT_EXTRACTION, "extractor_unavailable")),
    (EmptyExtractionError, (EXIT_EXTRACTION, "empty_extraction")),
    (ProviderError, (EXIT_PROVIDER, "provider_error")),
    (JobCancelledError, (EXIT_CANCELLED, "cancelled")),
]


def classify(exc: BaseException) -> tuple[int, str]:
    """Resolve ``exc`` to ``(exit_code, slug)``."""
    for typ, result in _MAP:
        if isinstance(exc, typ):
            return result
    if isinstance(exc, WikiError):
        return EXIT_ERROR, "wiki_error"
    return EXIT_ERROR, "error"


def render_error(exc: BaseException, *, as_json: bool) -> int:
    """Print ``exc`` to stderr (JSON envelope when ``as_json``) and return its code.

    Stdout is never touched, so a ``--json`` consumer sees an empty stdout on
    failure and the structured error on stderr. Unmapped exceptions print only a
    short message unless ``LLMWIKI_DEBUG=1`` is set (then the traceback is kept).
    """
    code, slug = classify(exc)
    message = str(exc).strip() or exc.__class__.__name__
    if as_json:
        envelope = {"error": {"code": slug, "exit_code": code, "message": message}}
        print(json.dumps(envelope, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)
    if slug in {"wiki_error", "error"} and os.environ.get("LLMWIKI_DEBUG") == "1":
        import traceback  # noqa: PLC0415

        traceback.print_exception(exc, file=sys.stderr)
    return code


def handle_errors[F: Callable[..., object]](fn: F) -> F:
    """Wrap a CLI command so typed domain errors become standard exit codes.

    Lets ``typer.Exit`` (already-coded) pass through untouched; maps
    ``WikiError`` and ``KeyboardInterrupt`` via :func:`render_error`. Works under
    ``CliRunner`` (which invokes the Typer app) as well as the real entry point.
    ``functools.wraps`` preserves the signature so Typer still builds the options.
    """

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        # Click invokes the callback with params as kwargs, so the command's own
        # ``as_json`` is authoritative; sys.argv is the fallback for the real
        # entry point (under CliRunner sys.argv is pytest's, not the invocation).
        as_json = bool(kwargs.get("as_json")) or "--json" in sys.argv
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except KeyboardInterrupt:
            print("Aborted.", file=sys.stderr)
            raise typer.Exit(EXIT_CANCELLED) from None
        except WikiError as exc:
            raise typer.Exit(render_error(exc, as_json=as_json)) from None

    return wrapper  # type: ignore[return-value]
