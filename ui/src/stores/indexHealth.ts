import { create } from "zustand"
import { api } from "@/lib/api"
import type { IndexStatus } from "@/types"
import { toast } from "sonner"

/**
 * Index health store (#306): owns the `IndexStatus` snapshot shared by the
 * global drift banner (AppShell), the index card in InsightsView, and the one
 * in SettingsView. Fetches are cheap; we just re-poll when a component asks.
 *
 * The reindex action calls `api.reindex()` (which enqueues an `index` job) and
 * follows the SSE stream so the busy flag clears on terminal events. Callers
 * can refresh on demand — for example the card auto-refreshes after reindex.
 */
interface IndexHealthState {
  status: IndexStatus | null
  busy: boolean
  error: string | null
  /** Fetch (or re-fetch) the snapshot. Safe to call concurrently. */
  refresh: () => Promise<void>
  /**
   * Enqueue a reindex and follow its SSE stream. On success/error/cancel,
   * refreshes the status so the UI reflects the new drift and `last_reindex_at`.
   */
  reindex: (embeddings?: boolean) => Promise<void>
}

export const useIndexHealthStore = create<IndexHealthState>((set, get) => ({
  status: null,
  busy: false,
  error: null,

  refresh: async () => {
    try {
      const status = await api.indexStatus()
      // Don't clobber `busy` mid-reindex.
      set({ status, error: null })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) })
    }
  },

  reindex: async (embeddings = true) => {
    if (get().busy) return
    set({ busy: true })
    // streamJob resolves on any terminal event — including a failed/cancelled
    // job — so capture those instead of always reporting success (#316).
    let failure: string | null = null
    try {
      const { job_id } = await api.reindex(embeddings)
      // Follow the SSE stream so the busy flag clears at the right moment.
      await api.streamJob(job_id, {
        onError: (m) => {
          failure = m
        },
        onCancelled: () => {
          failure = "cancelled"
        },
      })
      await get().refresh()
      if (failure) toast.error(`Reindex failed: ${failure}`)
      else toast.success("Index rebuilt")
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      toast.error(`Reindex failed: ${msg}`)
    } finally {
      set({ busy: false })
    }
  },
}))