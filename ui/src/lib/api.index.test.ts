import { describe, it, expect, vi, afterEach } from "vitest"
import { api } from "./api"

afterEach(() => vi.restoreAllMocks())

describe("api.indexStatus (#306)", () => {
  it("GETs /index/status and parses the drift + embeddings payload", async () => {
    const payload = {
      db_pages: 0,
      disk_files: 178,
      drift: 178,
      stale: true,
      embeddings: { count: 0, expected: 0, enabled: false },
      last_reindex_at: null,
    }
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => payload,
        }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await api.indexStatus()

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain("/index/status")
    expect(init?.method).toBeUndefined()
    expect(result).toEqual(payload)
  })
})

describe("api.reindex (#306)", () => {
  it("POSTs /index/reindex with default embeddings=true and returns the job id", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ job_id: 42 }),
        }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await api.reindex()

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain("/index/reindex")
    expect(init?.method).toBe("POST")
    const body = JSON.parse(String(init?.body))
    expect(body).toEqual({ embeddings: true })
    expect(result).toEqual({ job_id: 42 })
  })

  it("POSTs /index/reindex with embeddings=false when requested", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ job_id: 7 }),
        }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)

    await api.reindex(false)

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body).toEqual({ embeddings: false })
  })
})