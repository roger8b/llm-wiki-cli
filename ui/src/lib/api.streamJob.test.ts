import { describe, it, expect, vi, afterEach } from "vitest"
import { api } from "./api"

function streamResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder()
      for (const f of frames) controller.enqueue(enc.encode(f))
      controller.close()
    },
  })
  return { ok: true, body, status: 200 } as unknown as Response
}

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

afterEach(() => vi.restoreAllMocks())

describe("api.streamJob", () => {
  it("dispatches progress then result events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamResponse([
          sse("progress", { progress: "running_agent" }),
          sse("progress", { progress: "creating_change_request" }),
          sse("result", { result: '{"answer":"hi"}' }),
        ]),
      ),
    )
    const progress: string[] = []
    let result: string | null = null
    await api.streamJob(1, {
      onProgress: (s) => progress.push(s),
      onResult: (r) => {
        result = r
      },
    })
    expect(progress).toEqual(["running_agent", "creating_change_request"])
    expect(result).toBe('{"answer":"hi"}')
  })

  it("dispatches token events before the final result (#191)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamResponse([
          sse("progress", { progress: "running_agent" }),
          sse("token", { text: "Hel" }),
          sse("token", { text: "lo" }),
          sse("result", { result: '{"answer":"Hello world"}' }),
        ]),
      ),
    )
    const tokens: string[] = []
    let result: string | null = null
    await api.streamJob(1, {
      onToken: (t) => tokens.push(t),
      onResult: (r) => {
        result = r
      },
    })
    expect(tokens).toEqual(["Hel", "lo"])
    expect(result).toBe('{"answer":"Hello world"}')
  })

  it("dispatches the cancelled event as terminal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamResponse([
          sse("progress", { progress: "running_agent" }),
          sse("cancelled", { result: '{"cancelled":true}' }),
        ]),
      ),
    )
    let cancelled: string | null = null
    let resulted = false
    await api.streamJob(1, {
      onCancelled: (r) => {
        cancelled = r
      },
      onResult: () => {
        resulted = true
      },
    })
    expect(cancelled).toBe('{"cancelled":true}')
    expect(resulted).toBe(false)
  })

  it("dispatches ingest_event frames to onIngestEvent (#274)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamResponse([
          sse("ingest_event", {
            id: 1,
            kind: "step",
            ts: "t",
            payload: { name: "extracting", status: "start" },
          }),
          sse("ingest_event", {
            id: 2,
            kind: "page_write",
            ts: "t",
            payload: { path: "wiki/concepts/rag.md", op: "create", pages_staged: 1 },
          }),
          sse("result", { result: '{"cr":"CR-1"}' }),
        ]),
      ),
    )
    const kinds: string[] = []
    await api.streamJob(1, {
      onIngestEvent: (ev) => kinds.push(ev.kind),
      onResult: () => {},
    })
    expect(kinds).toEqual(["step", "page_write"])
  })

  it("passes after_event_id as a query param for reconnect (#274)", async () => {
    const fetchMock = vi.fn(async () => streamResponse([sse("result", { result: null })]))
    vi.stubGlobal("fetch", fetchMock)
    await api.streamJob(7, { onResult: () => {} }, 42)
    expect(String(fetchMock.mock.calls[0][0])).toContain("/jobs/7/events?after_event_id=42")
  })
})
