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
})
