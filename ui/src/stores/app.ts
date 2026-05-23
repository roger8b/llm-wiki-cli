import { create } from "zustand"
import { api } from "@/lib/api"
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
  /** Sync brains + active from backend API. */
  fetchBrains: () => Promise<void>
  /** Switch the active brain on the backend, then locally. */
  activateBrain: (id: string) => Promise<void>
}

export const useAppStore = create<AppState>()((set) => ({
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
      fetchBrains: async () => {
        set({ brainLoading: true })
        try {
          // Backend is the source of truth for which brain is active.
          const [brains, backendActive] = await Promise.all([
            api.listBrains(),
            api.getActiveBrain().catch(() => null),
          ])
          const active =
            brains.find((b) => b.id === backendActive?.id) ?? brains[0] ?? null
          set({
            brains,
            activeBrainId: active?.id ?? null,
            brainName: active?.name ?? "",
            brainLoading: false,
          })
        } catch {
          set({ brainLoading: false })
        }
      },
      activateBrain: async (id) => {
        await api.setActiveBrain(id)
        const b = useAppStore.getState().brains.find((x) => x.id === id)
        set({ activeBrainId: id, brainName: b?.name ?? "" })
      },
}))