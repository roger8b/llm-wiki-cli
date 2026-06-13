import { describe, it, expect } from "vitest"
import { slugify, pagePath } from "./slug"

// Reference outputs computed from the backend core.markdown.slugify (#187).
const PARITY: [string, string][] = [
  ["Use sqlite-vec", "use-sqlite-vec"],
  ["Decisão: usar Café & Açúcar!", "decisao-usar-cafe-acucar"],
  ["RAG  (v2)", "rag-v2"],
  ["Über Ältère", "uber-altere"],
  ["--Hello--", "hello"],
  ["100% Done", "100-done"],
]

describe("slugify (parity with backend)", () => {
  it.each(PARITY)("%s → %s", (input, expected) => {
    expect(slugify(input)).toBe(expected)
  })
})

describe("pagePath", () => {
  it("builds the typed wiki path", () => {
    expect(pagePath("decision", "Use sqlite-vec")).toBe(
      "wiki/decisions/use-sqlite-vec.md",
    )
    expect(pagePath("concept", "RAG")).toBe("wiki/concepts/rag.md")
  })
})
