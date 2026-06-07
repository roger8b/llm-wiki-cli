import { create } from "zustand"
import { api } from "@/lib/api"

type IngestStatus = "idle" | "running" | "done" | "error"
type FileStatus = "queued" | "running" | "done" | "error"

export interface BatchItem {
  name: string
  status: FileStatus
  detail?: string | null
}

interface IngestState {
  open: boolean
  title: string
  steps: string[]
  status: IngestStatus
  crId: string | null
  error: string | null
  /** Per-file progress for batch ingests (empty for single-file runs). */
  items: BatchItem[]
  /** Run an ingest-like task while showing an animated progress drawer. */
  run: (
    title: string,
    task: () => Promise<any>,
  ) => Promise<void>
  /**
   * Ingest multiple files: dispatch a batch request, then poll each returned
   * job_id independently, updating per-file status. Pre-validation errors from
   * the API are surfaced immediately on the matching file.
   */
  runBatch: (
    files: { name: string; path: string }[],
    dispatch: (paths: string[]) => Promise<{
      job_ids: number[]
      errors: { path: string; detail: string }[]
    }>,
  ) => Promise<void>
  close: () => void
}

// Cosmetic steps revealed while the (synchronous or asynchronous) backend call runs.
const FAKE_STEPS = [
  "Reading source…",
  "Searching existing wiki for context…",
  "Agent writing pages…",
]

function parseCrId(result: string | null | undefined): string | null {
  if (!result) return null
  try {
    const parsed = JSON.parse(result)
    return parsed.change_request_id || parsed.cr || null
  } catch {
    return null
  }
}

export const useIngestStore = create<IngestState>((set, get) => ({
  open: false,
  title: "",
  steps: [],
  status: "running", // start in running state if open
  crId: null,
  error: null,
  items: [],

  run: async (title, task) => {
    set({
      open: true,
      title,
      steps: [],
      status: "running",
      crId: null,
      error: null,
      items: [],
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
            clearInterval(timer)
            set({ status: "done", crId: parseCrId(job.result) })
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

  runBatch: async (files, dispatch) => {
    set({
      open: true,
      title: `Ingesting ${files.length} file${files.length > 1 ? "s" : ""}`,
      steps: [],
      status: "running",
      crId: null,
      error: null,
      items: files.map((f) => ({ name: f.name, status: "queued" as FileStatus })),
    })

    const setItem = (name: string, patch: Partial<BatchItem>) => {
      set({
        items: get().items.map((it) =>
          it.name === name ? { ...it, ...patch } : it,
        ),
      })
    }

    let res
    try {
      res = await dispatch(files.map((f) => f.path))
    } catch (e) {
      set({ status: "error", error: (e as Error).message })
      return
    }

    // Surface pre-validation errors immediately on the matching file.
    for (const err of res.errors) {
      const match = files.find((f) => f.path === err.path)
      if (match) setItem(match.name, { status: "error", detail: err.detail })
    }

    // Pair each successful job_id with its file (paths minus errored ones,
    // in dispatch order — the API preserves input order for valid paths).
    const erroredPaths = new Set(res.errors.map((e) => e.path))
    const queuedFiles = files.filter((f) => !erroredPaths.has(f.path))
    const jobOf = new Map<string, number>()
    queuedFiles.forEach((f, idx) => {
      if (idx < res.job_ids.length) jobOf.set(f.name, res.job_ids[idx])
    })

    await Promise.all(
      [...jobOf.entries()].map(async ([name, jobId]) => {
        while (true) {
          const job = await api.getJob(jobId)
          if (job.status === "running") {
            setItem(name, { status: "running" })
          } else if (job.status === "done") {
            setItem(name, { status: "done", detail: parseCrId(job.result) })
            break
          } else if (job.status === "error") {
            setItem(name, { status: "error", detail: job.error || "Job failed" })
            break
          }
          await new Promise((resolve) => setTimeout(resolve, 1000))
        }
      }),
    )

    const anyError = get().items.some((it) => it.status === "error")
    set({ status: anyError ? "error" : "done" })
  },

  close: () => set({ open: false, status: "idle", items: [] }),
}))
