import { describe, it, expect } from "vitest"
import { looksLikeUrl } from "./CaptureView"

describe("looksLikeUrl", () => {
  it("accepts bare http/https URLs", () => {
    expect(looksLikeUrl("https://example.com")).toBe(true)
    expect(looksLikeUrl("http://example.com/a/b?c=1")).toBe(true)
    expect(looksLikeUrl("  https://example.com  ")).toBe(true) // trimmed
  })

  it("rejects text, multi-word, and non-http schemes", () => {
    expect(looksLikeUrl("just some notes")).toBe(false)
    expect(looksLikeUrl("read https://example.com later")).toBe(false)
    expect(looksLikeUrl("ftp://example.com")).toBe(false)
    expect(looksLikeUrl("")).toBe(false)
    expect(looksLikeUrl("example.com")).toBe(false) // no scheme
  })
})
