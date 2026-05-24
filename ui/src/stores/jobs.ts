import { create } from "zustand"
import { api } from "@/lib/api"
import type { Job } from "@/types"
import { useAppStore } from "./app"

interface JobState {
  jobs: Job[]
  loading: boolean
  error: string | null
  fetch: () => Promise<void>
}

function syncActiveJobsBadge(jobs: Job[]) {
  const activeCount = jobs.filter(
    (j) => j.status === "running" || j.status === "queued"
  ).length
  useAppStore.getState().setActiveJobs(activeCount)
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  loading: false,
  error: null,

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
}))
