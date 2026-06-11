"""Audio extractor: offline batch transcription via faster-whisper.

Turns meetings, talks and voice notes into text, 100% offline (optional
``[audio]`` extra). Inserts ``[hh:mm:ss]`` anchors roughly every minute so the
ingestion agent can cite timestamps. Transcription is slow, so the ingest
service runs this INSIDE the job and reports ``transcribing`` progress.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from ...core.errors import EmptyExtractionError, ExtractorUnavailableError
from .base import ExtractedSource

# Audio files we know how to transcribe.
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")

# Drop a citation anchor at least every this many seconds.
_ANCHOR_INTERVAL = 60


def _load_faster_whisper() -> Any:
    try:
        import faster_whisper  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise ExtractorUnavailableError(
            "Audio support requires faster-whisper. "
            "Install it with: pip install 'llm-wiki[audio]'"
        ) from exc
    return faster_whisper


def _fmt_ts(seconds: float) -> str:
    s = int(max(0.0, seconds))
    return f"[{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}]"


def _format_segments(segments: Iterable[Any], *, interval: int = _ANCHOR_INTERVAL) -> str:
    """Join segment texts, inserting ``[hh:mm:ss]`` anchors ~every ``interval`` s.

    Pure and dependency-free: ``segments`` only needs ``.start`` (seconds) and
    ``.text`` attributes, so it is unit-testable without faster-whisper.
    """
    parts: list[str] = []
    next_anchor = 0.0
    for seg in segments:
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue
        start = float(getattr(seg, "start", 0.0) or 0.0)
        if start >= next_anchor:
            parts.append(_fmt_ts(start))
            next_anchor = (int(start // interval) + 1) * interval
        parts.append(text)
    return " ".join(parts).strip()


def transcribe(
    path: Path,
    *,
    model: str = "small",
    language: str | None = None,
    compute_type: str = "int8",
    progress: Callable[[str], None] | None = None,
) -> ExtractedSource:
    """Transcribe an audio file to an ``ExtractedSource`` (CPU/int8 by default).

    ``progress`` is an optional callback for status updates. Raises
    ``ExtractorUnavailableError`` if faster-whisper is missing and
    ``EmptyExtractionError`` if no speech was detected.
    """
    faster_whisper = _load_faster_whisper()
    if progress is not None:
        progress(f"loading whisper model '{model}'")
    whisper = faster_whisper.WhisperModel(model, device="cpu", compute_type=compute_type)
    if progress is not None:
        progress("transcribing")
    segments, _info = whisper.transcribe(str(path), language=language)
    text = _format_segments(segments)
    if not text.strip():
        raise EmptyExtractionError(
            f"No speech detected in {path.name} (silent or unsupported audio)."
        )
    return ExtractedSource(text=text, title=path.stem)


def extract(path: Path) -> ExtractedSource:
    """Registry entrypoint — transcribe with default settings (small/autodetect)."""
    return transcribe(path)
