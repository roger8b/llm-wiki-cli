import { create } from "zustand"

interface AppState {
  /** Live count of pending change requests (drives the Review badge). */
  pendingCount: number
  /** Active background jobs (drives the Jobs badge). */
  activeJobs: number
  /** Currently selected brain name (from ~/.wiki/brains/). */
  brainName: string
  /** ⌘K command palette visibility. */
  cmdkOpen: boolean
  setPendingCount: (n: number) => void
  setActiveJobs: (n: number) => void
  setBrainName: (name: string) => void
  setCmdkOpen: (open: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  pendingCount: 0,
  activeJobs: 0,
  brainName: "my-brain",
  cmdkOpen: false,
  setPendingCount: (n) => set({ pendingCount: n }),
  setActiveJobs: (n) => set({ activeJobs: n }),
  setBrainName: (name) => set({ brainName: name }),
  setCmdkOpen: (open) => set({ cmdkOpen: open }),
}))
