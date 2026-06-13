import { describe, it, expect, vi, afterEach } from "vitest"
import { api } from "./api"

afterEach(() => vi.restoreAllMocks())

function ok(json: unknown) {
  return vi.fn(
    async () => ({ ok: true, status: 200, json: async () => json }) as unknown as Response,
  )
}

describe("api tag navigation (#189)", () => {
  it("listPages(tag) encodes the tag query param", async () => {
    const fetchMock = ok([])
    vi.stubGlobal("fetch", fetchMock)
    await api.listPages("a b")
    expect(String(fetchMock.mock.calls[0][0])).toContain("/wiki/pages?tag=a%20b")
  })

  it("listPages() with no tag hits the unfiltered endpoint", async () => {
    const fetchMock = ok([])
    vi.stubGlobal("fetch", fetchMock)
    await api.listPages()
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/wiki\/pages$/)
  })

  it("listTags fetches the tag cloud", async () => {
    const fetchMock = ok([{ tag: "rag", count: 2 }])
    vi.stubGlobal("fetch", fetchMock)
    const tags = await api.listTags()
    expect(String(fetchMock.mock.calls[0][0])).toContain("/wiki/tags")
    expect(tags[0]).toEqual({ tag: "rag", count: 2 })
  })
})
