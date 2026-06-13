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
    vi.spyOn(api, "getJob").mockResolvedValue({
      id: 1,
      type: "ingest",
      status: "done",
      progress: null,
      result: JSON.stringify({ cr: "CR-1", files: 0, note: "The agent wrote none." }),
      error: null,
    } as never)

    await useIngestStore.getState().run("Ingesting x", async () => ({ job_id: 1 }))

    const s = useIngestStore.getState()
    expect(s.status).toBe("done")
    expect(s.crId).toBe("CR-1")
    expect(s.note).toBe("The agent wrote none.")
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
