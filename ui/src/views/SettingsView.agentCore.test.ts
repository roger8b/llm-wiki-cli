import { describe, it, expect } from "vitest"
import { normalizeAgentCore } from "./SettingsView"

// factory.py only branches on `agent_core == "minimal"`, so any other value
// (including a typo written by hand) runs DeepAgents. The select must show
// that same effective core instead of an out-of-enum option.
describe("normalizeAgentCore (#369)", () => {
  it("keeps the two valid cores", () => {
    expect(normalizeAgentCore("deepagents")).toBe("deepagents")
    expect(normalizeAgentCore("minimal")).toBe("minimal")
  })

  it("falls back to deepagents for unknown, empty or missing values", () => {
    expect(normalizeAgentCore("Minimal")).toBe("deepagents") // case-sensitive, like the backend
    expect(normalizeAgentCore("nonsense")).toBe("deepagents")
    expect(normalizeAgentCore("")).toBe("deepagents")
    expect(normalizeAgentCore(undefined)).toBe("deepagents")
    expect(normalizeAgentCore(null)).toBe("deepagents")
  })
})
