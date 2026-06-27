"""Tests for ``core/diff.py`` ``make_diff`` (issue #331).

Pins down 3 subtle behaviors that are not covered directly anywhere else:

1. **Empty diff early return** — ``old == new`` returns ``""``.
2. **Trailing newline normalization** — input without a final ``\\n`` gets
   one appended, so diff hunks stay well-formed (no ``-b+B`` concatenation,
   no ``\\ No newline at end of file`` markers).
3. **Path labels in unified-diff header** — ``fromfile=f"a/{path}"`` and
   ``tofile=f"b/{path}"`` so the diff renders meaningfully in the CR review
   UI.

These exist alongside the indirect coverage in ``test_cr_edit.py``, which
exercises ``make_diff`` via the CR service integration path; the tests here
pin down the unit-level contracts that an integration test wouldn't notice
if a refactor (#329 PathGuard mixin, future generalisations) accidentally
removed them.
"""

from __future__ import annotations

from llmwiki.core.diff import make_diff


def test_no_diff_when_unchanged() -> None:
    """Behavior 1 (defensive): identical input returns ``""``.

    Covers the AC edge case ``make_diff("", "", "x.md")`` too — ``""`` ==
    ``""`` triggers the early return. ``difflib.unified_diff`` alone also
    returns nothing for identical inputs, so this is a defensive
    double-check rather than a load-bearing guard, but it's documented in
    the spec and we pin it down.
    """
    assert make_diff("a\n", "a\n", "x.md") == ""
    assert make_diff("", "", "x.md") == ""


def test_trailing_newline_added_to_old_when_missing() -> None:
    """Behavior 2a: ``old`` without trailing ``\\n`` gets one appended.

    Without the normalization in ``diff.py:21-24``, the diff output would
    have ``-b+B`` concatenated on a single physical line (hunks malformed).
    Verified empirically in the issue's micro-benchmark: removing the
    normalization produces `` a\\n-b+B\\n`` instead of `` a\\n-b\\n+B\\n``.
    """
    result = make_diff("a\nb", "a\nB", "x.md")
    assert "-b\n+B" in result, f"hunk lines got concatenated: {result!r}"


def test_trailing_newline_added_to_new_when_missing() -> None:
    """Behavior 2b: ``new`` without trailing ``\\n`` gets one appended.

    Without it, difflib emits a ``\\ No newline at end of file`` marker at
    the end of the diff. The diff is still technically valid but ugly in
    the CR review UI and confusing to downstream tooling that expects a
    clean trailing newline.
    """
    result = make_diff("a\nb\n", "a\nB", "x.md")
    assert result.endswith("+B\n"), f"expected clean '...+B\\n', got: {result!r}"
    assert "No newline at end" not in result


def test_creation_old_empty() -> None:
    """``old=""`` produces a creation diff with ``+`` lines and path headers.

    Used by the CR service when a new page is created (and indirectly by
    the dedup guardrail in #167 firing on would-be duplicate titles).
    """
    result = make_diff("", "# New\n", "wiki/x.md")
    assert "a/wiki/x.md" in result
    assert "b/wiki/x.md" in result
    assert "+# New" in result


def test_deletion_new_empty() -> None:
    """``new=""`` produces a deletion diff with ``-`` lines and path headers.

    Used by ``services/page_delete_service.py:116`` to render the diff
    shown in CR review when a page is removed.
    """
    result = make_diff("old content\n", "", "wiki/x.md")
    assert "a/wiki/x.md" in result
    assert "b/wiki/x.md" in result
    assert "-old content" in result


def test_path_in_both_headers() -> None:
    """Behavior 3: ``path`` argument appears in the unified-diff headers.

    Without this, ``difflib`` defaults to empty ``fromfile``/``tofile`` and
    the diff header is ``--- \\n+++ \\n`` — useless in the CR review UI.
    """
    result = make_diff("a", "b", "wiki/concepts/foo.md")
    assert "--- a/wiki/concepts/foo.md" in result
    assert "+++ b/wiki/concepts/foo.md" in result
