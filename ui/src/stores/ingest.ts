import { create } from "zustand"
import { api } from "@/lib/api"

type IngestStatus = "idle" | "running" | "done" | "error"

interface IngestState {
  open: boolean
  title: string
  steps: string[]
  status: IngestStatus
  crId: string | null
  error: string | null
  /** Run an ingest-like task while showing an animated progress drawer. */
  run: (
    title: string,
    task: () => Promise<any>,
  ) => Promise<void>
  close: () => void
}

// Cosmetic steps revealed while the (synchronous or asynchronous) backend call runs.
const FAKE_STEPS = [
  "Reading source…",
  "Searching existing wiki for context…",
  "Agent writing pages…",
]

export const useIngestStore = create<IngestState>((set, get) => ({
  open: false,
  title: "",
  steps: [],
  status: "running", // start in running state if open
  crId: null,
  error: null,

  run: async (title, task) => {
    set({
      open: true,
      title,
      steps: [],
      status: "running",
      crId: null,
      error: null,
    })

    // staggered reveal of cosmetic steps
    let i = 0
    const timer = setInterval(() => {
      if (get().status !== "running" || i >= FAKE_STEPS.length) {
        clearInterval(timer)
        return
      }
      set({ steps: [...get().steps, FAKE_STEPS[i]] })
      i++
    }, 800)

    try {
      const res = await task()
      
      if (res && typeof res === "object" && "job_id" in res) {
        const jobId = res.job_id
        // Poll job status
        while (true) {
          const job = await api.getJob(jobId)
          if (job.status === "done") {
            let change_request_id = null
            if (job.result) {
              try {
                const parsed = JSON.parse(job.result)
                change_request_id = parsed.change_request_id || parsed.cr || null
              } catch {
                // ignore
              }
            }
            clearInterval(timer)
            set({ status: "done", crId: change_request_id })
            break
          } else if (job.status === "error") {
            clearInterval(timer)
            set({ status: "error", error: job.error || "Job failed" })
            break
          }
          await new Promise((resolve) => setTimeout(resolve, 1000))
        }
      } else {
        const change_request_id = res ? (res as any).change_request_id : null
        clearInterval(timer)
        set({ status: "done", crId: change_request_id })
      }
    } catch (e) {
      clearInterval(timer)
      set({ status: "error", error: (e as Error).message })
    }
  },

  close: () => set({ open: false, status: "idle" }),
}))
