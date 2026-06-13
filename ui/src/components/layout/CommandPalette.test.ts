import { describe, it, expect, vi, afterEach } from "vitest"
import type { ReactElement } from "react"
import { renderSnippet } from "./CommandPalette"
import { api } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

describe("renderSnippet (#188)", () => {
  it("turns «…» markers into <mark> and keeps the rest as <span>", () => {
    const nodes = renderSnippet("a «hit» b «two» c") as ReactElement[]
    const types = nodes.map((n) => n.type)
    // span, mark, span, mark, span
    expect(types).toEqual(["span", "mark", "span", "mark", "span"])
    const marks = nodes.filter((n) => n.type === "mark")
    expect(marks.map((m) => (m.props as { children: string }).children)).toEqual([
      "hit",
      "two",
    ])
  })

  it("no markers → single span", () => {
    const nodes = renderSnippet("plain text") as ReactElement[]
    expect(nodes).toHaveLength(1)
    expect(nodes[0].type).toBe("span")
  })
})

describe("api.search (#188)", () => {
  it("requests q + limit and forwards the abort signal", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({ ok: true, status: 200, json: async () => [] }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)
    const ctrl = new AbortController()

    await api.search("vector store", 8, ctrl.signal)

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain("/search?q=vector%20store&limit=8")
    expect(init?.signal).toBe(ctrl.signal)
  })
})
