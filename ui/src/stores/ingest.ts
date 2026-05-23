import { create } from "zustand"

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
    task: () => Promise<{ change_request_id: string | null }>,
  ) => Promise<void>
  close: () => void
}

// Cosmetic steps revealed while the (synchronous) backend call runs. The real
// ingest is blocking, so these are illustrative, not a true stream.
const FAKE_STEPS = [
  "Reading source…",
  "Searching existing wiki for context…",
  "Agent writing pages…",
]

export const useIngestStore = create<IngestState>((set, get) => ({
  open: false,
  title: "",
  steps: [],
  status: "idle",
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
      const { change_request_id } = await task()
      clearInterval(timer)
      set({ status: "done", crId: change_request_id })
    } catch (e) {
      clearInterval(timer)
      set({ status: "error", error: (e as Error).message })
    }
  },

  close: () => set({ open: false, status: "idle" }),
}))
