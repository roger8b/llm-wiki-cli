from __future__ import annotations

import pytest

from llmwiki.core import frontmatter
from llmwiki.core.errors import InvalidFrontmatterError


class TestFrontmatter:
    def test_parses_meta_and_body(self) -> None:
        text = "---\ntitle: Foo\ntags: [a, b]\n---\n\n# Foo\ncorpo"
        meta, body = frontmatter.parse(text)
        assert meta == {"title": "Foo", "tags": ["a", "b"]}
        assert body.startswith("# Foo")

    def test_no_frontmatter_returns_empty_meta(self) -> None:
        text = "# Sem frontmatter\nconteúdo"
        meta, body = frontmatter.parse(text)
        assert meta == {}
        assert body == text

    def test_unterminated_fence_is_not_frontmatter(self) -> None:
        text = "---\ntitle: Foo\nsem fechamento"
        meta, body = frontmatter.parse(text)
        assert meta == {}
        assert body == text

    def test_invalid_yaml_raises(self) -> None:
        text = "---\ntitle: : :\n  - bad\n---\nbody"
        with pytest.raises(InvalidFrontmatterError):
            frontmatter.parse(text)

    def test_non_mapping_yaml_raises(self) -> None:
        text = "---\n- just\n- a\n- list\n---\nbody"
        with pytest.raises(InvalidFrontmatterError):
            frontmatter.parse(text)

    def test_dump_roundtrip(self) -> None:
        meta = {"title": "Foo", "tags": ["x"]}
        body = "# Foo\ncorpo"
        out = frontmatter.dump(meta, body)
        parsed_meta, parsed_body = frontmatter.parse(out)
        assert parsed_meta == meta
        assert parsed_body.strip() == body

    def test_dump_without_meta_returns_body(self) -> None:
        assert frontmatter.dump({}, "só corpo") == "só corpo"
