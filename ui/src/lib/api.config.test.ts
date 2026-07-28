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

describe("api.patchConfig — ask path (#368)", () => {
  it("PATCHes ask_mode and its RAG knobs", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({ ok: true, status: 200, json: async () => ({}) }) as unknown as Response,
    )
    vi.stubGlobal("fetch", fetchMock)

    await api.patchConfig({
      ask_mode: "rag",
      ask_rag_top_k: 8,
      ask_rag_max_context_chars: 12000,
    })

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(String(init?.body))).toMatchObject({
      ask_mode: "rag",
      ask_rag_top_k: 8,
      ask_rag_max_context_chars: 12000,
    })
  })
})
