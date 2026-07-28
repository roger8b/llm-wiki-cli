import { describe, it, expect } from "vitest"
import { normalizeAskMode } from "./SettingsView"

// The backend degrades unknown ask_mode values to "agent"
// (query_service.py:230); the Settings select must render the same fallback
// instead of an empty/out-of-enum option.
describe("normalizeAskMode (#368)", () => {
  it("keeps the three valid modes", () => {
    expect(normalizeAskMode("agent")).toBe("agent")
    expect(normalizeAskMode("rag")).toBe("rag")
    expect(normalizeAskMode("auto")).toBe("auto")
  })

  it("falls back to agent for unknown, empty or missing values", () => {
    expect(normalizeAskMode("nonsense")).toBe("agent")
    expect(normalizeAskMode("")).toBe("agent")
    expect(normalizeAskMode(undefined)).toBe("agent")
    expect(normalizeAskMode(null)).toBe("agent")
  })
})
