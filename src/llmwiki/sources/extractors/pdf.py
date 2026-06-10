"""PDF extractor: pulls the text layer with pypdf (optional extra ``[pdf]``)."""

from __future__ import annotations

import re
from pathlib import Path

from ...core.errors import EmptyExtractionError, ExtractorUnavailableError

# Below this many characters we assume the PDF has no real text layer
# (e.g. a scanned document) and refuse rather than feed garbage to the LLM.
_MIN_CHARS = 50

# A lowercase word split across a line by a hyphen: "continua-\nção".
_HYPHEN_BREAK = re.compile(r"([a-zà-ÿ]+)-\n([a-zà-ÿ]+)")

# 3 or more consecutive newlines (allowing surrounding whitespace).
_EXTRA_BLANKS = re.compile(r"\n[ \t]*\n[ \t]*(\n[ \t]*)+")


def _postprocess(text: str) -> str:
    """Mend end-of-line hyphenation and collapse excessive blank lines."""
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _EXTRA_BLANKS.sub("\n\n", text)
    return text.strip()


def extract(path: Path) -> str:
    """Extract text from a PDF, one page at a time, joined by blank lines.

    Raises ``ExtractorUnavailableError`` if pypdf is missing and
    ``EmptyExtractionError`` if the PDF has no usable text layer.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        # Only treat a *missing pypdf* as "install the extra". Re-raise any other
        # import failure (e.g. a broken pypdf dependency) so it isn't masked.
        if getattr(exc, "name", None) == "pypdf" or "pypdf" in str(exc):
            raise ExtractorUnavailableError(
                "PDF support requires pypdf. Install it with: pip install 'llm-wiki[pdf]'"
            ) from exc
        raise

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = _postprocess("\n\n".join(pages))
    if len(text) < _MIN_CHARS:
        raise EmptyExtractionError(
            f"No text layer found in {path.name} (extracted {len(text)} chars). "
            "It is likely a scanned PDF; OCR is out of scope."
        )
    return text
