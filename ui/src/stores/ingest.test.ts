import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { useIngestStore } from "./ingest"
import { api } from "@/lib/api"

describe("useIngestStore.cancel", () => {
  beforeEach(() => {
    useIngestStore.setState({ jobIds: [], cancelling: false })
  })
  afterEach(() => vi.restoreAllMocks())

  it("cancels every tracked job and sets cancelling", async () => {
    const spy = vi.spyOn(api, "cancelJob").mockResolvedValue({
      job_id: 0,
      status: "running",
      cancel_requested: true,
    })
    useIngestStore.setState({ jobIds: [11, 22] })

    await useIngestStore.getState().cancel()

    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenCalledWith(11)
    expect(spy).toHaveBeenCalledWith(22)
    expect(useIngestStore.getState().cancelling).toBe(true)
  })

  it("is a no-op when there are no jobs", async () => {
    const spy = vi.spyOn(api, "cancelJob")
    await useIngestStore.getState().cancel()
    expect(spy).not.toHaveBeenCalled()
  })
})

describe("useIngestStore.run note (#237 follow-up)", () => {
  afterEach(() => vi.restoreAllMocks())

  it("surfaces the empty-CR note from the job result", async () => {
    // run() now drives the job over SSE (#274): the terminal `result` arrives
    // via onResult, and the note is parsed from that result string.
    vi.spyOn(api, "streamJob").mockImplementation(async (_id, h) => {
      h.onResult?.(JSON.stringify({ cr: "CR-1", files: 0, note: "The agent wrote none." }))
    })

    await useIngestStore.getState().run("Ingesting x", async () => ({ job_id: 1 }))

    const s = useIngestStore.getState()
    expect(s.status).toBe("done")
    expect(s.crId).toBe("CR-1")
    expect(s.note).toBe("The agent wrote none.")
  })

  it("surfaces the skipped reason when dedup short-circuits the run", async () => {
    // Mirrors the worker's payload on SourceAlreadyProcessedError — the agent
    // never ran, so the UI must NOT show the misleading "no changes proposed".
    vi.spyOn(api, "streamJob").mockImplementation(async (_id, h) => {
      h.onResult?.(
        JSON.stringify({
          skipped: true,
          reason:
            "Source already processed (hash abc123…): raw/articles/x.md. " +
            "Use force=True to re-ingest.",
        }),
      )
    })

    await useIngestStore.getState().run("Ingesting x", async () => ({ job_id: 2 }))

    const s = useIngestStore.getState()
    expect(s.status).toBe("done")
    expect(s.crId).toBeNull()
    expect(s.note).toContain("Skipped:")
    expect(s.note).toContain("Source already processed")
  })

  it("builds a live timeline from ingest events and finishes done", async () => {
    vi.spyOn(api, "streamJob").mockImplementation(async (_id, h) => {
      h.onIngestEvent?.({
        id: 1, kind: "step", ts: "t",
        payload: { name: "running_agent", status: "start", pages_staged: 0 },
      })
      h.onIngestEvent?.({
        id: 2, kind: "page_write", ts: "t",
        payload: { path: "wiki/concepts/rag.md", op: "create", pages_staged: 1 },
      })
      h.onResult?.(JSON.stringify({ cr: "CR-2", files: 1 }))
    })

    await useIngestStore.getState().run("Ingesting x", async () => ({ job_id: 3 }))

    const s = useIngestStore.getState()
    expect(s.status).toBe("done")
    expect(s.crId).toBe("CR-2")
    expect(s.events).toHaveLength(2)
    expect(s.pagesStaged).toBe(1)
  })
})

describe("useIngestStore minimize/reopen", () => {
  it("close keeps the run state so it can be reopened", () => {
    useIngestStore.setState({ open: true, status: "running", title: "Ingesting x", crId: null })
    useIngestStore.getState().close()
    let s = useIngestStore.getState()
    expect(s.open).toBe(false)
    expect(s.status).toBe("running") // state preserved
    expect(s.title).toBe("Ingesting x")

    useIngestStore.getState().reopen()
    s = useIngestStore.getState()
    expect(s.open).toBe(true)
    expect(s.status).toBe("running")
  })

  it("clear fully resets the run", () => {
    useIngestStore.setState({ open: true, status: "done", crId: "CR-1", jobIds: [9] })
    useIngestStore.getState().clear()
    const s = useIngestStore.getState()
    expect(s.open).toBe(false)
    expect(s.status).toBe("idle")
    expect(s.crId).toBeNull()
    expect(s.jobIds).toEqual([])
  })
})
