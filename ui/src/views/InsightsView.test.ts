import { describe, expect, it } from "vitest"
import type { ModelStats } from "@/types"
import { fmtCost, fmtNum, fmtPct, summarize } from "./InsightsView"

function stat(over: Partial<ModelStats>): ModelStats {
  return {
    model: "m",
    runs: 1,
    tokens_in_avg: 0,
    tokens_in_p95: 0,
    tokens_out_avg: 0,
    tokens_out_p95: 0,
    latency_ms_avg: 0,
    latency_ms_p95: 0,
    fallback_rate: 0,
    phantom_rate: 0,
    applied: 0,
    rejected: 0,
    est_cost_usd: null,
    ...over,
  }
}

describe("formatters", () => {
  it("fmtNum abbreviates thousands", () => {
    expect(fmtNum(950)).toBe("950")
    expect(fmtNum(4200)).toBe("4.2k")
  })

  it("fmtCost handles null and zero", () => {
    expect(fmtCost(null)).toBe("—")
    expect(fmtCost(0)).toBe("$0")
    expect(fmtCost(1.5)).toBe("$1.50")
    expect(fmtCost(0.0012)).toBe("$0.0012")
  })

  it("fmtPct rounds to whole percent", () => {
    expect(fmtPct(0.083)).toBe("8%")
  })
})

describe("summarize", () => {
  it("aggregates runs, tokens, cost and rates weighted by runs", () => {
    const t = summarize([
      stat({ runs: 2, tokens_in_avg: 100, tokens_out_avg: 50, fallback_rate: 0.5, est_cost_usd: 0, applied: 1, rejected: 1 }),
      stat({ runs: 1, tokens_in_avg: 1000, tokens_out_avg: 500, fallback_rate: 0, est_cost_usd: 0.5, applied: 1, rejected: 0 }),
    ])
    expect(t.runs).toBe(3)
    // (150*2) + (1500*1)
    expect(t.tokens).toBe(1800)
    expect(t.cost).toBe(0.5)
    expect(t.hasCost).toBe(true)
    // weighted: (0.5*2 + 0*1) / 3
    expect(t.fallback).toBeCloseTo(1 / 3)
    // rejected 1 of (applied 2 + rejected 1)
    expect(t.rejRate).toBeCloseTo(1 / 3)
  })

  it("empty stats are zeroed and costless", () => {
    const t = summarize([])
    expect(t.runs).toBe(0)
    expect(t.hasCost).toBe(false)
    expect(t.fallback).toBe(0)
  })
})
