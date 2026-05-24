"""CLI commands — split by domain."""

from .brain import brain_app
from .ingest import ingest
from .mcp import mcp
from .page import page_app
from .review import apply, jobs, reject, review
from .serve import serve
from .source import source_app
from .wiki import ask, index, lint, log, maintain, search

__all__ = [
    "brain_app",
    "source_app",
    "page_app",
    "ask",
    "apply",
    "ingest",
    "index",
    "jobs",
    "lint",
    "log",
    "maintain",
    "mcp",
    "reject",
    "review",
    "search",
    "serve",
]