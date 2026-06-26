import { describe, it, expect } from "vitest"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { DriftBanner } from "./DriftBanner"

function render(stale: boolean, drift = 178) {
  return renderToStaticMarkup(
    createElement(DriftBanner, { stale, drift, onReindex: () => {} }),
  )
}

describe("DriftBanner (#306)", () => {
  it("renders nothing when the index is not stale", () => {
    expect(render(false, 0)).toBe("")
  })

  it("renders a single-line warning with the drift count when stale", () => {
    const html = render(true, 178)
    expect(html).toContain("Index is out of date")
    expect(html).toContain("178")
    expect(html).toContain("Reindex")
  })
})