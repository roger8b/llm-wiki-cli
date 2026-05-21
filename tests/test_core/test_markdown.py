from __future__ import annotations

from llmwiki.core import markdown


class TestExtractWikilinks:
    def test_none(self) -> None:
        assert markdown.extract_wikilinks("sem links aqui") == []

    def test_single(self) -> None:
        assert markdown.extract_wikilinks("veja [[RAG]] ali") == ["RAG"]

    def test_multiple_dedup_preserves_order(self) -> None:
        text = "[[A]] e [[B]] e de novo [[A]]"
        assert markdown.extract_wikilinks(text) == ["A", "B"]

    def test_piped_link_target_only(self) -> None:
        assert markdown.extract_wikilinks("[[Alvo|texto exibido]]") == ["Alvo"]

    def test_ignores_links_in_html_comments(self) -> None:
        text = "real [[X]]\n<!-- placeholder [[Y]] -->"
        assert markdown.extract_wikilinks(text) == ["X"]


class TestExtractTitle:
    def test_first_h1(self) -> None:
        assert markdown.extract_title("intro\n# Título\n## Sub") == "Título"

    def test_no_h1(self) -> None:
        assert markdown.extract_title("## Só sub\ntexto") is None


class TestSlugify:
    def test_basic(self) -> None:
        assert (
            markdown.slugify("Retrieval Augmented Generation")
            == "retrieval-augmented-generation"
        )

    def test_accents_and_symbols(self) -> None:
        assert markdown.slugify("Decisão: RAG vs. Wiki!") == "decisao-rag-vs-wiki"
