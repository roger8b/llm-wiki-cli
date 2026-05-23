import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"
import type { BrainConfig, RegisteredBrain } from "@/types"

interface AppState {
  /** Live count of pending change requests (drives the Review badge). */
  pendingCount: number
  /** Active background jobs (drives the Jobs badge). */
  activeJobs: number
  /** Currently selected brain name (from registered brains). */
  brainName: string
  /** ⌘K command palette visibility. */
  cmdkOpen: boolean
  /** null = unknown (loading), true/false = whether to show onboarding. */
  needsOnboarding: boolean | null
  /** Whether brainName is still loading from the backend. */
  brainLoading: boolean
  /** Registered brains configuration. */
  brains: RegisteredBrain[]
  /** ID of the active brain. */
  activeBrainId: string | null
  setPendingCount: (n: number) => void
  setActiveJobs: (n: number) => void
  setBrainName: (name: string) => void
  setCmdkOpen: (open: boolean) => void
  setNeedsOnboarding: (v: boolean) => void
  setBrainLoading: (loading: boolean) => void
  setBrains: (brains: RegisteredBrain[]) => void
  setActiveBrainId: (id: string | null) => void
  addBrain: (brain: RegisteredBrain) => void
  updateBrain: (id: string, updates: Partial<BrainConfig>) => void
  removeBrain: (id: string) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      pendingCount: 0,
      activeJobs: 0,
      brainName: "",
      cmdkOpen: false,
      needsOnboarding: null,
      brainLoading: false,
      brains: [],
      activeBrainId: null,
      setPendingCount: (n) => set({ pendingCount: n }),
      setActiveJobs: (n) => set({ activeJobs: n }),
      setBrainName: (name) => set({ brainName: name }),
      setCmdkOpen: (open) => set({ cmdkOpen: open }),
      setNeedsOnboarding: (v) => set({ needsOnboarding: v }),
      setBrainLoading: (loading) => set({ brainLoading: loading }),
      setBrains: (brains) => set({ brains }),
      setActiveBrainId: (id) => set({ activeBrainId: id }),
      addBrain: (brain) => set((s) => ({ brains: [...s.brains, brain] })),
      updateBrain: (id, updates) =>
        set((s) => ({
          brains: s.brains.map((b) => (b.id === id ? { ...b, ...updates } : b)),
        })),
      removeBrain: (id) =>
        set((s) => {
          const remaining = s.brains.filter((b) => b.id !== id)
          // Auto-select first remaining brain if active was deleted
          const newActiveId =
            s.activeBrainId === id ? (remaining[0]?.id ?? null) : s.activeBrainId
          const newActiveBrain = remaining.find((b) => b.id === newActiveId)
          return {
            brains: remaining,
            activeBrainId: newActiveId,
            brainName: newActiveBrain?.name ?? s.brainName,
          }
        }),
    }),
    {
      name: "llm-wiki-brains",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        brains: state.brains,
        activeBrainId: state.activeBrainId,
        brainName: state.brainName,
      }),
    },
  ),
)