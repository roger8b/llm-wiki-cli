import { create } from "zustand"
import { api } from "@/lib/api"
import type { IngestEvent } from "@/types"

type IngestStatus = "idle" | "running" | "done" | "error" | "cancelled"
type FileStatus = "queued" | "running" | "done" | "error" | "cancelled"

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
  /** Why the run produced no CR (empty-result explanation from the backend). */
  note: string | null
  error: string | null
  /** Per-file progress for batch ingests (empty for single-file runs). */
  items: BatchItem[]
  /** Live ingestion timeline events for the current single-file run (#274). */
  events: IngestEvent[]
  /** Pages written to staging so far (from the latest event that carried it). */
  pagesStaged: number
  /** Job ids backing the current run (1 for single, N for batch) — for cancel. */
  jobIds: number[]
  /** True once the user has requested cancellation of the current run. */
  cancelling: boolean
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
  /** Request cooperative cancellation of every running job in this run. */
  cancel: () => Promise<void>
  /** Hide the drawer but KEEP the run state so it can be reopened. */
  close: () => void
  /** Re-show the drawer for the current/last run. */
  reopen: () => void
  /** Fully discard the run state (hide + reset). */
  clear: () => void
}

// Cosmetic steps shown until the backend reports a real progress step.
const FAKE_STEPS = [
  "Reading source…",
  "Searching existing wiki for context…",
  "Agent writing pages…",
]

// Human labels for the backend's coarse progress steps.
const PROGRESS_LABELS: Record<string, string> = {
  running_agent: "Agent reading & writing pages…",
  creating_change_request: "Preparing the change request…",
}

function progressLabel(step: string | null | undefined): string | null {
  if (!step) return null
  return PROGRESS_LABELS[step] ?? step
}

function parseCrId(result: string | null | undefined): string | null {
  if (!result) return null
  try {
    const parsed = JSON.parse(result)
    return parsed.change_request_id || parsed.cr || null
  } catch {
    return null
  }
}

/** Reason an ingest produced no CR, set by the backend (#237 follow-up). */
function parseNote(result: string | null | undefined): string | null {
  if (!result) return null
  try {
    const parsed = JSON.parse(result)
    // Backend's ingest_service sets `note` when the agent ran but wrote nothing.
    // The worker sets `skipped` + `reason` when content-hash dedup short-
    // circuited the run (#237 follow-up: re-ingest UX). Surface both so the UI
    // never falls back to the misleading "Done — no changes proposed." string.
    if (typeof parsed.note === "string") return parsed.note
    if (parsed.skipped) {
      return parsed.reason
        ? `Skipped: ${parsed.reason}`
        : "Skipped — source was already ingested. Use Re-ingest to force the agent to run again."
    }
    return null
  } catch {
    return null
  }
}

/** A human label for a step event's machine name (reuses PROGRESS_LABELS). */
function stepLabel(name: string | undefined): string | null {
  if (!name) return null
  return PROGRESS_LABELS[name] ?? name
}

export const useIngestStore = create<IngestState>((set, get) => ({
  open: false,
  title: "",
  steps: [],
  status: "idle",
  crId: null,
  note: null,
  error: null,
  items: [],
  events: [],
  pagesStaged: 0,
  jobIds: [],
  cancelling: false,

  run: async (title, task) => {
    set({
      open: true,
      title,
      steps: [],
      status: "running",
      crId: null,
      note: null,
      error: null,
      items: [],
      events: [],
      pagesStaged: 0,
      jobIds: [],
      cancelling: false,
    })

    // staggered reveal of cosmetic steps (until a real progress step arrives)
    let i = 0
    const timer = setInterval(() => {
      if (get().status !== "running" || i >= FAKE_STEPS.length) {
        clearInterval(timer)
        return
      }
      // Don't keep adding cosmetic steps once the backend reports real progress.
      if (get().jobIds.length > 0 && get().steps.length > 0) return
      set({ steps: [...get().steps, FAKE_STEPS[i]] })
      i++
    }, 800)

    try {
      const res = await task()

      if (res && typeof res === "object" && "job_id" in res) {
        const jobId = res.job_id
        set({ jobIds: [jobId] })
        // Live timeline over SSE (#274): tool calls, page writes, telemetry and
        // step durations stream in instead of a 1s poll on a single label.
        let lastResult: string | null = null
        let terminal: "cancelled" | "error" | null = null
        await api.streamJob(jobId, {
          onProgress: (step) => {
            // Fallback label for backends that only set coarse progress.
            const label = progressLabel(step)
            if (label && get().events.length === 0) {
              clearInterval(timer)
              set({ steps: [label] })
            }
          },
          onIngestEvent: (ev) => {
            clearInterval(timer)
            const events = [...get().events, ev]
            const patch: Partial<IngestState> = { events }
            const staged = ev.payload?.pages_staged
            if (typeof staged === "number") patch.pagesStaged = staged
            // Mirror step labels into the legacy `steps` list for the drawer.
            if (ev.kind === "step" && ev.payload?.status !== "end") {
              const label = stepLabel(ev.payload?.name)
              if (label) patch.steps = [...get().steps.filter(Boolean), label]
            }
            set(patch)
          },
          onResult: (result) => {
            lastResult = result
          },
          onCancelled: () => {
            terminal = "cancelled"
          },
          onError: (msg) => {
            terminal = "error"
            set({ error: msg })
          },
        })
        clearInterval(timer)
        if (terminal === "cancelled") {
          set({ status: "cancelled" })
        } else if (terminal === "error") {
          set({ status: "error", error: get().error || "Job failed" })
        } else {
          set({
            status: "done",
            crId: parseCrId(lastResult),
            note: parseNote(lastResult),
          })
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
      note: null,
      error: null,
      items: files.map((f) => ({ name: f.name, status: "queued" as FileStatus })),
      events: [],
      pagesStaged: 0,
      jobIds: [],
      cancelling: false,
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
    set({ jobIds: [...jobOf.values()] })

    await Promise.all(
      [...jobOf.entries()].map(async ([name, jobId]) => {
        while (true) {
          const job = await api.getJob(jobId)
          if (job.status === "running") {
            setItem(name, { status: "running", detail: progressLabel(job.progress) })
          } else if (job.status === "done") {
            setItem(name, { status: "done", detail: parseCrId(job.result) })
            break
          } else if (job.status === "cancelled") {
            setItem(name, { status: "cancelled", detail: "cancelled" })
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
    const allCancelled =
      get().items.length > 0 && get().items.every((it) => it.status === "cancelled")
    set({ status: anyError ? "error" : allCancelled ? "cancelled" : "done" })
  },

  cancel: async () => {
    const ids = get().jobIds
    if (ids.length === 0) return
    set({ cancelling: true })
    await Promise.allSettled(ids.map((id) => api.cancelJob(id)))
  },

  // Hide but keep state so the run can be reopened (and a finished run reviewed).
  close: () => set({ open: false }),
  reopen: () => set({ open: true }),
  clear: () =>
    set({
      open: false,
      status: "idle",
      steps: [],
      crId: null,
      note: null,
      error: null,
      items: [],
      events: [],
      pagesStaged: 0,
      jobIds: [],
      cancelling: false,
    }),
}))
