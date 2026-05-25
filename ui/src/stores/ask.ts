import { create } from "zustand"
import type { QueryResult } from "@/types"

// Persists the Ask screen's content across navigation. AskView is unmounted when
// the user switches tabs, so keeping the question/answer in local component state
// lost it on return — this store survives the unmount.
interface AskState {
  /** Current question text in the composer. */
  question: string
  /** The answer currently shown (live result or an opened history item). */
  result: QueryResult | null
  /** ask_history id of the shown answer (for promote linking / highlight). */
  activeId: number | null
  /** True while a query is in flight. In the store (not local state) so the
   *  loading UI survives navigating away and back mid-query. */
  loading: boolean
  setQuestion: (q: string) => void
  setResult: (r: QueryResult | null) => void
  setActiveId: (id: number | null) => void
  setLoading: (loading: boolean) => void
}

export const useAskStore = create<AskState>((set) => ({
  question: "",
  result: null,
  activeId: null,
  loading: false,
  setQuestion: (question) => set({ question }),
  setResult: (result) => set({ result }),
  setActiveId: (activeId) => set({ activeId }),
  setLoading: (loading) => set({ loading }),
}))
