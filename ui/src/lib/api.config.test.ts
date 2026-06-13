import { describe, it, expect, vi, afterEach } from "vitest"
import { api } from "./api"

afterEach(() => vi.restoreAllMocks())

describe("api.patchConfig (#237)", () => {
  it("PATCHes the new config fields to /config", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({ ok: true, status: 200, json: async () => ({}) }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)

    await api.patchConfig({
      model: "ollama:llama3.1",
      embedding_model: "ollama:nomic-embed-text",
      chunk_size_chars: 9000,
      agent_fix_retries: 2,
      whisper_model: "base",
      whisper_language: null,
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain("/config")
    expect(init?.method).toBe("PATCH")
    const body = JSON.parse(String(init?.body))
    expect(body).toMatchObject({
      embedding_model: "ollama:nomic-embed-text",
      chunk_size_chars: 9000,
      agent_fix_retries: 2,
      whisper_model: "base",
      whisper_language: null,
    })
  })
})
