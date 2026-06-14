"""TokenBuffer coalescing (#191)."""

from __future__ import annotations

from llmwiki.llm_agents.streaming import TokenBuffer


def test_flushes_on_char_threshold() -> None:
    flushes: list[str] = []
    clk = [0.0]
    buf = TokenBuffer(flushes.append, max_chars=10, max_interval=999, clock=lambda: clk[0])
    for tok in ["ab", "cd", "ef"]:  # 6 chars, below 10 → no flush yet
        buf.add(tok)
    assert flushes == []
    buf.add("ghij")  # now 10 chars → flush full accumulated text
    assert flushes == ["abcdefghij"]


def test_flushes_on_time_threshold() -> None:
    flushes: list[str] = []
    clk = [0.0]
    buf = TokenBuffer(flushes.append, max_chars=999, max_interval=0.1, clock=lambda: clk[0])
    buf.add("a")  # under both thresholds
    assert flushes == []
    clk[0] = 0.2  # time advanced past interval
    buf.add("b")
    assert flushes == ["ab"]


def test_manual_flush_and_text() -> None:
    flushes: list[str] = []
    buf = TokenBuffer(flushes.append, max_chars=999, max_interval=999, clock=lambda: 0.0)
    buf.add("hello")
    buf.add(" world")
    assert flushes == []  # neither threshold hit
    buf.flush()
    assert flushes == ["hello world"]
    assert buf.text == "hello world"


def test_flush_is_noop_without_pending() -> None:
    flushes: list[str] = []
    buf = TokenBuffer(flushes.append, clock=lambda: 0.0)
    buf.flush()
    buf.add("")  # empty token ignored
    buf.flush()
    assert flushes == []


def test_does_not_emit_per_token() -> None:
    flushes: list[str] = []
    clk = [0.0]
    buf = TokenBuffer(flushes.append, max_chars=40, max_interval=999, clock=lambda: clk[0])
    for _ in range(30):  # 30 single-char tokens, threshold 40
        buf.add("x")
    # Far fewer flushes than tokens (coalesced); at most 1 here.
    assert len(flushes) <= 1
