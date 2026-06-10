"""Agent middleware.

``ExcludeToolsMiddleware`` strips named tools from the model request *after* the
DeepAgents ``FilesystemMiddleware`` has injected its built-ins. We use it to hide
the ``execute`` (shell) tool: ``ChangeRequestBackend`` does not implement
``execute``, so it only ever returns an error — exposing it wastes context and
invites the model to try shell commands that cannot work here.

``CancellationMiddleware`` aborts a run at the next model-call boundary when a
user-supplied probe reports the job was cancelled.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from ..core.errors import JobCancelledError

# Built-in tools that make no sense for this app's read/stage-only backend.
EXCLUDED_TOOLS = frozenset({"execute"})


def _name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        n = tool.get("name")
        return n if isinstance(n, str) else None
    n = getattr(tool, "name", None)
    return n if isinstance(n, str) else None


class ExcludeToolsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Remove tools by name before they reach the model."""

    def __init__(self, excluded: frozenset[str] = EXCLUDED_TOOLS) -> None:
        self._excluded = excluded

    def _filter(self, request: Any) -> Any:
        if not self._excluded:
            return request
        kept = [t for t in request.tools if _name(t) not in self._excluded]
        return request.override(tools=kept)

    def wrap_model_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Any:
        return handler(self._filter(request))

    async def awrap_model_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        return await handler(self._filter(request))


class CancellationMiddleware(AgentMiddleware[Any, Any, Any]):
    """Abort the agent run cooperatively before each model call.

    ``check`` is polled at every model-call boundary (between tool loops). When it
    returns True we raise ``JobCancelledError`` instead of calling the model, so
    an in-flight job stops within one step instead of running to completion.
    """

    def __init__(self, check: Callable[[], bool]) -> None:
        self._check = check

    def _guard(self) -> None:
        if self._check():
            raise JobCancelledError("Job cancelled by user.")

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        self._guard()
        return handler(request)

    async def awrap_model_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        self._guard()
        return await handler(request)
