"""CLI commands — split by domain."""

from .brain import brain_app
from .evals import evals_app
from .ingest import ingest
from .mcp import mcp
from .page import page_app
from .review import apply, jobs_app, reject, review
from .serve import serve
from .skills import skills_app
from .source import source_app
from .wiki import ask, autolink, index, lint, log, maintain, search

__all__ = [
    "brain_app",
    "evals_app",
    "source_app",
    "page_app",
    "skills_app",
    "ask",
    "apply",
    "autolink",
    "ingest",
    "index",
    "jobs_app",
    "lint",
    "log",
    "maintain",
    "mcp",
    "reject",
    "review",
    "search",
    "serve",
]