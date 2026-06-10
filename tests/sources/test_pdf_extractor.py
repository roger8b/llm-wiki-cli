"""Tests for the PDF extractor (issue #160)."""

from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

import pytest

from llmwiki.core.errors import EmptyExtractionError, ExtractorUnavailableError
from llmwiki.sources.extractors import extract_text
from llmwiki.sources.extractors import pdf as pdf_extractor

# Tests that actually parse a PDF need the optional [pdf] extra. The core must
# work without it, so they skip when pypdf is absent (CI installs the extra).
_HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
requires_pypdf = pytest.mark.skipif(
    not _HAS_PYPDF, reason="pypdf not installed (the [pdf] extra)"
)


def _make_pdf(pages: list[str]) -> bytes:
    """Build a minimal multi-page PDF with a real text layer (no binary fixture)."""
    objs: list[bytes] = []
    n_pages = len(pages)
    font_num = 3 + 2 * n_pages
    kids_nums = [3 + 2 * i for i in range(n_pages)]

    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{k} 0 R" for k in kids_nums)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    for i, text in enumerate(pages):
        content_num = kids_nums[i] + 1
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {content_num} 0 R >>".encode()
        )
        esc = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 700 Td ({esc}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode()
    return out


@requires_pypdf
def test_extract_multipage_preserves_paragraphs(tmp_path: Path) -> None:
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(
        _make_pdf(
            [
                "First page about retrieval augmented generation systems.",
                "Second page about vector databases and embeddings.",
            ]
        )
    )
    text = pdf_extractor.extract(doc)
    assert "retrieval augmented generation" in text
    assert "vector databases" in text
    # Pages joined by a blank line.
    assert "\n\n" in text


@requires_pypdf
def test_extract_text_dispatches_to_pdf(tmp_path: Path) -> None:
    doc = tmp_path / "x.pdf"
    doc.write_bytes(
        _make_pdf(["Dispatch through the extractor registry works fine for PDF files."])
    )
    assert "Dispatch through the extractor registry" in extract_text(doc)


def test_hyphenation_postprocess() -> None:
    # The post-processor is pure — no pypdf needed.
    assert pdf_extractor._postprocess("conti-\nnuation of word") == "continuation of word"


@requires_pypdf
def test_hyphenation_is_mended(tmp_path: Path) -> None:
    doc = tmp_path / "hyph.pdf"
    doc.write_bytes(_make_pdf(["plain text without any hyphen breaks at all in this line."]))
    assert "hyphen" in pdf_extractor.extract(doc)


def test_collapses_excess_blank_lines() -> None:
    assert pdf_extractor._postprocess("a\n\n\n\nb") == "a\n\nb"


@requires_pypdf
def test_scanned_pdf_raises_empty(tmp_path: Path) -> None:
    doc = tmp_path / "scan.pdf"
    doc.write_bytes(_make_pdf(["hi"]))  # < 50 chars of text
    with pytest.raises(EmptyExtractionError):
        pdf_extractor.extract(doc)


def test_missing_pypdf_raises_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(_make_pdf(["some text long enough to pass the threshold easily here."]))
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "pypdf":
            raise ImportError("No module named 'pypdf'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ExtractorUnavailableError, match="llm-wiki\\[pdf\\]"):
        pdf_extractor.extract(doc)
