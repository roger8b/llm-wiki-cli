"""Tests for the audio extractor (issue #76) — faster-whisper mocked."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from pathlib import Path

import pytest

from llmwiki.core.errors import EmptyExtractionError, ExtractorUnavailableError
from llmwiki.sources.extractors import audio as audio_extractor
from llmwiki.sources.extractors import source_type


@dataclass
class _Seg:
    start: float
    text: str


class _FakeWhisperModel:
    """Stand-in for faster_whisper.WhisperModel — returns canned segments."""

    segments: list[_Seg] = []

    def __init__(self, model: str, device: str = "cpu", compute_type: str = "int8") -> None:
        self.model = model

    def transcribe(self, path: str, language: str | None = None):  # noqa: ANN201
        info = type("Info", (), {"language": language or "en", "duration": 0.0})()
        return iter(type(self).segments), info


def _fake_faster_whisper(segments: list[_Seg]):
    _FakeWhisperModel.segments = segments
    return type("FW", (), {"WhisperModel": _FakeWhisperModel})


# ── pure helpers ─────────────────────────────────────────────────────────────


def test_fmt_ts() -> None:
    assert audio_extractor._fmt_ts(0) == "[00:00:00]"
    assert audio_extractor._fmt_ts(61) == "[00:01:01]"
    assert audio_extractor._fmt_ts(3725) == "[01:02:05]"


def test_format_segments_inserts_periodic_anchors() -> None:
    segs = [
        _Seg(0.0, "hello there"),
        _Seg(10.0, "still first minute"),
        _Seg(75.0, "second minute now"),
        _Seg(140.0, "third minute"),
    ]
    out = audio_extractor._format_segments(segs)
    # One anchor at the start, then ~every 60s (not on every segment).
    assert out.count("[") == 3
    assert out.startswith("[00:00:00] hello there")
    assert "[00:01:" in out  # ~75s
    assert "[00:02:" in out  # ~140s
    assert "still first minute" in out


def test_format_segments_skips_empty() -> None:
    out = audio_extractor._format_segments([_Seg(0.0, "  "), _Seg(1.0, "real")])
    assert "real" in out


# ── transcribe (mocked model) ────────────────────────────────────────────────


def test_transcribe_returns_extracted_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        audio_extractor,
        "_load_faster_whisper",
        lambda: _fake_faster_whisper([_Seg(0.0, "meeting notes about the roadmap")]),
    )
    f = tmp_path / "standup.mp3"
    f.write_bytes(b"\x00")
    progress: list[str] = []
    src = audio_extractor.transcribe(f, progress=progress.append)
    assert "meeting notes about the roadmap" in src.text
    assert src.title == "standup"
    assert "transcribing" in progress


def test_transcribe_empty_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audio_extractor, "_load_faster_whisper", lambda: _fake_faster_whisper([])
    )
    f = tmp_path / "silence.wav"
    f.write_bytes(b"\x00")
    with pytest.raises(EmptyExtractionError):
        audio_extractor.transcribe(f)


def test_missing_faster_whisper_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *a: object, **k: object) -> object:
        if name == "faster_whisper":
            raise ImportError("No module named 'faster_whisper'")
        return real_import(name, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ExtractorUnavailableError, match=r"llm-wiki\[audio\]"):
        audio_extractor.transcribe(tmp_path / "x.mp3")


# ── registry / classification ────────────────────────────────────────────────


def test_whisper_config_defaults(tmp_path: Path) -> None:
    from llmwiki.core.config import WorkspaceConfig

    cfg = WorkspaceConfig(brain_root=tmp_path)
    assert cfg.whisper_model == "small"
    assert cfg.whisper_language is None


def test_source_type_audio() -> None:
    for ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
        assert source_type(Path(f"clip{ext}")) == "audio"


def test_registry_dispatches_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from llmwiki.sources.extractors import extract

    monkeypatch.setattr(
        audio_extractor,
        "_load_faster_whisper",
        lambda: _fake_faster_whisper([_Seg(0.0, "spoken content here")]),
    )
    f = tmp_path / "voice.m4a"
    f.write_bytes(b"\x00")
    src = extract(f)
    assert "spoken content here" in src.text


# ── ingest integration (audio runs inside the job, reports transcribing) ──────


def test_ingest_audio_reports_transcribing(brain, monkeypatch: pytest.MonkeyPatch) -> None:
    from llmwiki.core.config import WorkspaceConfig
    from llmwiki.db.connection import get_connection
    from llmwiki.db.repo import JobRepo
    from llmwiki.services import ingest_service

    monkeypatch.setattr(
        audio_extractor,
        "_load_faster_whisper",
        lambda: _fake_faster_whisper([_Seg(0.0, "the talk covered vector search")]),
    )
    f = brain.raw / "meetings" / "talk.m4a"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\x00")

    conn = get_connection(brain.db_path)
    jr = JobRepo(conn)
    jid = jr.create("ingest", status="running")
    steps: list[str] = []
    monkeypatch.setattr(jr, "set_progress", lambda j, s: steps.append(s))
    cfg = WorkspaceConfig(brain_root=brain.root, whisper_model="tiny")
    try:
        src = ingest_service._extract_for_job(f, cfg, jr, jid)
    finally:
        conn.close()
    assert "vector search" in src.text
    assert "transcribing" in steps
