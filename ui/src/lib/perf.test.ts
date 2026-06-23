import { describe, expect, it } from "vitest"
import { formatMs, parsePerf, stepLabel } from "./perf"

describe("stepLabel", () => {
  it("maps known steps and chunk passes", () => {
    expect(stepLabel("extracting")).toBe("Reading source")
    expect(stepLabel("chunk 2/3")).toBe("Chunk 2/3")
    expect(stepLabel("unknown_step")).toBe("unknown_step")
  })
})

describe("formatMs", () => {
  it("formats sub-second, seconds and minutes", () => {
    expect(formatMs(340)).toBe("340ms")
    expect(formatMs(1200)).toBe("1.2s")
    expect(formatMs(125000)).toBe("2m 05s")
    expect(formatMs(-1)).toBe("—")
  })
})

describe("parsePerf", () => {
  it("returns null without durations", () => {
    expect(parsePerf(null)).toBeNull()
    expect(parsePerf("not json")).toBeNull()
    expect(parsePerf(JSON.stringify({ files: 1 }))).toBeNull()
  })

  it("builds ordered segments with percentages and execution", () => {
    const result = JSON.stringify({
      durations_ms: { extracting: 100, "chunk 1/2": 200, creating_change_request: 100 },
      execution: { model: "anthropic:MiniMax-M3", tokens_in: 1000, tokens_out: 500, tool_calls: 7 },
    })
    const perf = parsePerf(result)!
    expect(perf).not.toBeNull()
    expect(perf.totalMs).toBe(400)
    // Order is preserved (pipeline order), not sorted by size.
    expect(perf.segments.map((s) => s.name)).toEqual([
      "extracting",
      "chunk 1/2",
      "creating_change_request",
    ])
    expect(perf.segments[1].label).toBe("Chunk 1/2")
    expect(perf.segments[1].pct).toBeCloseTo(50)
    expect(perf.tokensIn).toBe(1000)
    expect(perf.toolCalls).toBe(7)
    expect(perf.model).toBe("anthropic:MiniMax-M3")
  })

  it("tolerates missing execution block", () => {
    const perf = parsePerf(JSON.stringify({ durations_ms: { extracting: 50 } }))!
    expect(perf.totalMs).toBe(50)
    expect(perf.tokensIn).toBeNull()
    expect(perf.model).toBeNull()
  })
})
