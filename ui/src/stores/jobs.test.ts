import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { useJobStore } from "./jobs"
import { api } from "@/lib/api"

describe("useJobStore.cancel", () => {
  beforeEach(() => {
    useJobStore.setState({ jobs: [], error: null, cancellingIds: [] })
  })
  afterEach(() => vi.restoreAllMocks())

  it("cancels a job and refetches", async () => {
    const cancelSpy = vi
      .spyOn(api, "cancelJob")
      .mockResolvedValue({ job_id: 5, status: "running", cancel_requested: true })
    const listSpy = vi.spyOn(api, "listJobs").mockResolvedValue([])

    await useJobStore.getState().cancel(5)

    expect(cancelSpy).toHaveBeenCalledWith(5)
    expect(listSpy).toHaveBeenCalled()
    expect(useJobStore.getState().cancellingIds).toEqual([])
  })

  it("records the error and clears the cancelling flag on failure", async () => {
    vi.spyOn(api, "cancelJob").mockRejectedValue(new Error("boom"))

    await useJobStore.getState().cancel(7)

    expect(useJobStore.getState().error).toBe("boom")
    expect(useJobStore.getState().cancellingIds).toEqual([])
  })
})
