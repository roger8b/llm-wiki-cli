import { describe, it, expect, vi, afterEach } from "vitest"
import { asTags } from "./PageEditor"
import { api } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

describe("asTags (#186)", () => {
  it("normalizes arrays and strings, drops empties", () => {
    expect(asTags(["a", "b"])).toEqual(["a", "b"])
    expect(asTags("a, b  c")).toEqual(["a", "b", "c"])
    expect(asTags("")).toEqual([])
    expect(asTags(undefined)).toEqual([])
    expect(asTags(42)).toEqual([])
  })
})

describe("api.proposeEdit (#186)", () => {
  it("POSTs frontmatter + body to the page propose-edit endpoint", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ change_request_id: "CR-1", files_changed: 1 }),
        }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)

    const out = await api.proposeEdit(
      "wiki/concepts/rag.md",
      { title: "RAG", type: "concept" },
      "# RAG\nbody\n",
    )
    expect(out.change_request_id).toBe("CR-1")
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain("/wiki/pages/wiki/concepts/rag.md/propose-edit")
    expect(init?.method).toBe("POST")
    expect(JSON.parse(String(init?.body))).toEqual({
      frontmatter: { title: "RAG", type: "concept" },
      body: "# RAG\nbody\n",
    })
  })
})
