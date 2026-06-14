import { create } from "zustand"
import type { QueryResult } from "@/types"

// One exchange in the current conversation thread.
export interface AskTurn {
  question: string
  result: QueryResult
  /** ask_history id of this answer (promote linking / highlight). */
  historyId: number | null
}

// Persists the Ask screen's content across navigation. AskView is unmounted when
// the user switches tabs, so keeping the thread in local component state lost it
// on return — this store survives the unmount. The thread is a conversation
// (#190): each turn carries the prior context server-side via conversationId.
interface AskState {
  /** Current question text in the composer. */
  question: string
  /** Stacked exchanges of the active conversation (oldest first). */
  turns: AskTurn[]
  /** Server conversation id; null until the first answer of a new thread. */
  conversationId: string | null
  /** True while a query is in flight. In the store (not local state) so the
   *  loading UI survives navigating away and back mid-query. */
  loading: boolean
  setQuestion: (q: string) => void
  addTurn: (turn: AskTurn) => void
  setConversationId: (id: string | null) => void
  setLoading: (loading: boolean) => void
  /** Start a fresh conversation: clears thread + id, keeps the composer empty. */
  newConversation: () => void
  /** Load an existing conversation's turns into the thread. */
  loadConversation: (id: string | null, turns: AskTurn[]) => void
}

export const useAskStore = create<AskState>((set) => ({
  question: "",
  turns: [],
  conversationId: null,
  loading: false,
  setQuestion: (question) => set({ question }),
  addTurn: (turn) => set((s) => ({ turns: [...s.turns, turn] })),
  setConversationId: (conversationId) => set({ conversationId }),
  setLoading: (loading) => set({ loading }),
  newConversation: () => set({ turns: [], conversationId: null, question: "" }),
  loadConversation: (conversationId, turns) =>
    set({ conversationId, turns, question: "" }),
}))
