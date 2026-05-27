"""API routers — split by domain."""

from .ask import router as ask_router
from .brains import router as brains_router
from .changes import router as changes_router
from .cli import router as cli_router
from .config import router as config_router
from .jobs import router as jobs_router
from .onboarding import router as onboarding_router
from .providers import router as providers_router
from .query import router as query_router
from .search import router as search_router
from .skills import router as skills_router
from .sources import router as sources_router
from .wiki import router as wiki_router

__all__ = [
    "ask_router",
    "brains_router",
    "changes_router",
    "cli_router",
    "config_router",
    "jobs_router",
    "onboarding_router",
    "providers_router",
    "query_router",
    "search_router",
    "skills_router",
    "sources_router",
    "wiki_router",
]