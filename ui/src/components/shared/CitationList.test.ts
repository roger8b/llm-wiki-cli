import { describe, it, expect } from "vitest"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { CitationList } from "./CitationList"
import type { Citation } from "@/types"

function render(citations: Citation[]): string {
  return renderToStaticMarkup(
    createElement(MemoryRouter, null, createElement(CitationList, { citations })),
  )
}

describe("CitationList (#192)", () => {
  it("renders nothing without citations", () => {
    expect(render([])).toBe("")
  })

  it("renders a clickable page citation with its path", () => {
    const html = render([{ page: "wiki/concepts/rag.md" }])
    expect(html).toContain('data-testid="citation-page"')
    expect(html).toContain("wiki/concepts/rag.md")
    expect(html).toContain("rag") // friendly title from the filename
  })

  it("renders a source (raw/) citation distinctly", () => {
    const html = render([{ source: "raw/articles/x.md" }])
    expect(html).toContain('data-testid="citation-source"')
    expect(html).toContain("raw/articles/x.md")
  })

  it("renders an invalid citation as struck-through and non-clickable", () => {
    const html = render([{ page: "wiki/ghost.md", invalid: true }])
    expect(html).toContain('data-testid="citation-invalid"')
    expect(html).toContain("line-through")
    expect(html).not.toContain('data-testid="citation-page"')
  })

  it("renders a quote toggle when a quote is present", () => {
    const html = render([{ page: "wiki/concepts/rag.md", quote: "RAG retrieves docs." }])
    expect(html).toContain('data-testid="citation-quote-toggle"')
  })
})
