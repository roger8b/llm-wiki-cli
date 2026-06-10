import { create } from "zustand"
import { api } from "@/lib/api"
import type { Job } from "@/types"
import { useAppStore } from "./app"

interface JobState {
  jobs: Job[]
  loading: boolean
  error: string | null
  cancellingIds: number[]
  fetch: () => Promise<void>
  cancel: (id: number) => Promise<void>
}

function syncActiveJobsBadge(jobs: Job[]) {
  const activeCount = jobs.filter(
    (j) => j.status === "running" || j.status === "queued"
  ).length
  useAppStore.getState().setActiveJobs(activeCount)
}

export const useJobStore = create<JobState>((set, get) => ({
  jobs: [],
  loading: false,
  error: null,
  cancellingIds: [],

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const jobs = await api.listJobs()
      syncActiveJobsBadge(jobs)
      set({ jobs, loading: false })
    } catch (e) {
      set({ loading: false, error: (e as Error).message })
    }
  },

  cancel: async (id) => {
    set({ cancellingIds: [...get().cancellingIds, id] })
    try {
      await api.cancelJob(id)
      await get().fetch()
    } catch (e) {
      set({ error: (e as Error).message })
    } finally {
      set({ cancellingIds: get().cancellingIds.filter((x) => x !== id) })
    }
  },
}))
