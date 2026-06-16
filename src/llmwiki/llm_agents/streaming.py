"""Token streaming for the query agent (#191).

The query agent can stream its answer token-by-token. To avoid thousands of tiny
SSE events, :class:`TokenBuffer` coalesces tokens and flushes the *full
accumulated text* at most every ``max_chars`` characters or ``max_interval``
seconds. The worker's flush callback persists that text to ``jobs.stream_text``;
the SSE endpoint emits the delta as ``token`` events. The authoritative answer
still arrives in the final ``result`` event, which replaces the streamed preview.

A provider that does not stream (e.g. ``_NoStreamOllama`` forces ``stream=False``)
simply never fires ``on_llm_new_token`` — no tokens, no behaviour change.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class TokenBuffer:
    """Coalesce streamed tokens; flush the full text on size/time thresholds."""

    def __init__(
        self,
        flush: Callable[[str], None],
        *,
        max_chars: int = 40,
        max_interval: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._flush_cb = flush
        self._max_chars = max_chars
        self._max_interval = max_interval
        self._clock = clock
        self._acc = ""
        self._pending = 0
        self._last_flush = clock()

    def add(self, text: str) -> None:
        if not text:
            return
        self._acc += text
        self._pending += len(text)
        if self._pending >= self._max_chars or (
            self._clock() - self._last_flush >= self._max_interval
        ):
            self.flush()

    def flush(self) -> None:
        """Emit the full accumulated text if anything is pending."""
        if self._pending == 0:
            return
        self._flush_cb(self._acc)
        self._pending = 0
        self._last_flush = self._clock()

    @property
    def text(self) -> str:
        return self._acc


def _arg_preview(raw: Any, *, limit: int = 120) -> str:
    """Short, body-free preview of a tool's input for the event log (#272).

    Tool inputs to the ingestion agent are small (a query string, a page path),
    but ``write_file``/``edit_file`` carry the full page content — which must
    never reach the event log. We keep only the leading slice and, for dict
    inputs, drop obvious content fields.
    """
    if isinstance(raw, dict):
        trimmed = {
            k: v
            for k, v in raw.items()
            if k not in {"content", "new_string", "old_string", "new_content"}
        }
        text = ", ".join(f"{k}={v}" for k, v in trimmed.items())
    else:
        text = str(raw)
    text = " ".join(text.split())
    return text[:limit]


def make_ingestion_event_handler(on_event: Callable[[str, dict[str, Any]], None]) -> Any:
    """LangChain callback that turns tool calls into ``tool_start``/``tool_end``
    events for a job's live timeline (#272).

    Imported lazily (like :func:`make_token_handler`) so importing this module
    never requires langchain. Only metadata is forwarded — tool names and a
    trimmed, content-free argument preview — never page bodies.
    """
    from langchain_core.callbacks import BaseCallbackHandler  # noqa: PLC0415

    class _IngestionEventHandler(BaseCallbackHandler):
        def on_tool_start(
            self, serialized: dict[str, Any], input_str: str, **_: Any
        ) -> None:
            name = (serialized or {}).get("name", "tool")
            on_event("tool_start", {"tool": name, "args": _arg_preview(input_str)})

        def on_tool_end(self, output: Any, **kwargs: Any) -> None:
            name = kwargs.get("name") or "tool"
            on_event("tool_end", {"tool": name})

    return _IngestionEventHandler()


def make_token_handler(on_token: Callable[[str], None]) -> Any:
    """Build a LangChain callback handler that forwards new tokens to ``on_token``.

    Imported lazily so importing this module never requires langchain. Tool-call
    chatter from some providers may leak into the stream; that is acceptable —
    the final ``result`` event carries the authoritative answer and replaces the
    preview (documented in #191).
    """
    from langchain_core.callbacks import BaseCallbackHandler  # noqa: PLC0415

    class _TokenStreamHandler(BaseCallbackHandler):
        def on_llm_new_token(self, token: str, **_: Any) -> None:
            if token:
                on_token(token)

    return _TokenStreamHandler()
