import { describe, it, expect, beforeEach } from "vitest"
import { useAskStore } from "./ask"
import type { QueryResult } from "@/types"

const result = (answer: string): QueryResult => ({ answer, citations: [] })

describe("useAskStore", () => {
  beforeEach(() => {
    useAskStore.setState({ question: "", turns: [], conversationId: null, loading: false })
  })

  it("retains question / loading across setter calls (survives unmount)", () => {
    const s = useAskStore.getState()
    s.setQuestion("what is RAG?")
    s.setLoading(true)
    const after = useAskStore.getState()
    expect(after.question).toBe("what is RAG?")
    expect(after.loading).toBe(true)
  })

  it("stacks turns and tracks the conversation id", () => {
    const s = useAskStore.getState()
    s.addTurn({ question: "what is RAG?", result: result("a1"), historyId: 1 })
    s.setConversationId("conv-1")
    s.addTurn({ question: "trade-offs?", result: result("a2"), historyId: 2 })

    const after = useAskStore.getState()
    expect(after.turns).toHaveLength(2)
    expect(after.turns[0].question).toBe("what is RAG?")
    expect(after.turns[1].result.answer).toBe("a2")
    expect(after.conversationId).toBe("conv-1")
  })

  it("newConversation clears the thread and id", () => {
    const s = useAskStore.getState()
    s.addTurn({ question: "q", result: result("a"), historyId: 1 })
    s.setConversationId("conv-1")
    s.newConversation()

    const after = useAskStore.getState()
    expect(after.turns).toHaveLength(0)
    expect(after.conversationId).toBeNull()
    expect(after.question).toBe("")
  })

  it("loadConversation replaces the thread with the chosen turns", () => {
    const s = useAskStore.getState()
    s.loadConversation("conv-2", [
      { question: "old q", result: result("old a"), historyId: 5 },
    ])
    const after = useAskStore.getState()
    expect(after.conversationId).toBe("conv-2")
    expect(after.turns).toHaveLength(1)
    expect(after.turns[0].historyId).toBe(5)
  })
})
