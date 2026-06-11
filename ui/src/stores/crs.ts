import { create } from "zustand"
import { api } from "@/lib/api"
import type { ChangeRequest } from "@/types"
import { useAppStore } from "./app"

type DiffTab = "diff" | "after" | "before"

interface CrState {
  crs: ChangeRequest[]
  loading: boolean
  error: string | null
  selectedId: string | null
  selectedFileIdx: number
  tab: DiffTab
  /** CR id currently being applied/rejected (drives button spinners). */
  busyId: string | null
  /** Whether the "after" pane is in edit mode (#183). */
  editing: boolean

  fetch: () => Promise<void>
  select: (id: string) => void
  selectFile: (idx: number) => void
  setTab: (tab: DiffTab) => void
  setEditing: (editing: boolean) => void
  apply: (id: string) => Promise<void>
  reject: (id: string) => Promise<void>
  /** Edit one file's proposed content before apply (#183). */
  updateFile: (id: string, path: string, newContent: string) => Promise<void>
  /** Hydrate a CR's full `changes` (the list endpoint omits them). */
  ensureDetail: (id: string) => Promise<void>
}

function isPending(cr: ChangeRequest) {
  return cr.status === "pending_review"
}

function syncPendingBadge(crs: ChangeRequest[]) {
  useAppStore.getState().setPendingCount(crs.filter(isPending).length)
}

export const useCrStore = create<CrState>((set, get) => ({
  crs: [],
  loading: false,
  error: null,
  selectedId: null,
  selectedFileIdx: 0,
  tab: "diff",
  busyId: null,
  editing: false,

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const crs = await api.listChangeRequests()
      syncPendingBadge(crs)
      // keep current selection if still present, else first pending, else first
      const prev = get().selectedId
      const keep = prev && crs.some((c) => c.id === prev) ? prev : null
      const selectedId = keep ?? crs.find(isPending)?.id ?? crs[0]?.id ?? null
      set({ crs, loading: false, selectedId, selectedFileIdx: 0 })
      if (selectedId) void get().ensureDetail(selectedId)
    } catch (e) {
      set({ loading: false, error: (e as Error).message })
    }
  },

  select: (id) => {
    set({ selectedId: id, selectedFileIdx: 0, tab: "diff", editing: false })
    void get().ensureDetail(id)
  },
  selectFile: (idx) => set({ selectedFileIdx: idx, editing: false }),
  setTab: (tab) => set({ tab }),
  setEditing: (editing) => set({ editing }),

  ensureDetail: async (id) => {
    const cr = get().crs.find((c) => c.id === id)
    if (!cr || cr.changes.length > 0) return // already hydrated
    try {
      const full = await api.getChangeRequest(id)
      set({
        crs: get().crs.map((c) => (c.id === id ? { ...c, ...full } : c)),
      })
    } catch {
      // leave as-is; detail pane shows "No file changes."
    }
  },

  apply: async (id) => {
    if (get().busyId) return // already applying/rejecting something
    set({ busyId: id })
    try {
      await api.applyChangeRequest(id)
      settleCr(set, get, id, "applied")
    } finally {
      set({ busyId: null })
    }
  },

  reject: async (id) => {
    if (get().busyId) return
    set({ busyId: id })
    try {
      await api.rejectChangeRequest(id)
      settleCr(set, get, id, "rejected")
    } finally {
      set({ busyId: null })
    }
  },

  updateFile: async (id, path, newContent) => {
    const updated = await api.updateCrFile(id, path, newContent)
    set({
      crs: get().crs.map((c) => (c.id === id ? { ...c, ...updated } : c)),
    })
    syncPendingBadge(get().crs)
  },
}))

/** Mark a CR as applied/rejected, sync the badge, auto-select the next pending. */
function settleCr(
  set: (partial: Partial<CrState>) => void,
  get: () => CrState,
  id: string,
  status: "applied" | "rejected",
) {
  const crs = get().crs.map((c) =>
    c.id === id
      ? { ...c, status: status as ChangeRequest["status"], applied_at: new Date().toISOString() }
      : c,
  )
  syncPendingBadge(crs)

  // auto-select the next pending CR (after the settled one), else any pending
  const idx = crs.findIndex((c) => c.id === id)
  const after = crs.slice(idx + 1).find(isPending)
  const anyPending = crs.find(isPending)
  const nextId = (after ?? anyPending)?.id ?? id
  set({
    crs,
    selectedId: nextId,
    selectedFileIdx: 0,
    tab: "diff",
    editing: false,
  })
  // hydrate the newly selected CR's diffs (list endpoint omits `changes`)
  if (nextId !== id) void get().ensureDetail(nextId)
}

// ── selectors ──
export function selectedCr(s: CrState): ChangeRequest | null {
  return s.crs.find((c) => c.id === s.selectedId) ?? null
}
export function pendingCrs(s: CrState): ChangeRequest[] {
  return s.crs.filter(isPending)
}
export function settledCrs(s: CrState): ChangeRequest[] {
  return s.crs.filter((c) => !isPending(c))
}
