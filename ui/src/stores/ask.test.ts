import { describe, it, expect, beforeEach } from "vitest"
import { useAskStore } from "./ask"

describe("useAskStore", () => {
  beforeEach(() => {
    useAskStore.setState({ question: "", result: null, activeId: null, loading: false })
  })

  it("retains question / loading / result across setter calls (survives unmount)", () => {
    const s = useAskStore.getState()
    s.setQuestion("what is RAG?")
    s.setLoading(true)
    s.setActiveId(7)
    s.setResult({ answer: "an answer", citations: [] })

    const after = useAskStore.getState()
    expect(after.question).toBe("what is RAG?")
    expect(after.loading).toBe(true)
    expect(after.activeId).toBe(7)
    expect(after.result?.answer).toBe("an answer")
  })
})
