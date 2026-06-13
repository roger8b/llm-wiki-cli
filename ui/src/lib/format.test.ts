import { describe, it, expect } from "vitest"
import { timeAgo, pageTags, crKind, execLine, fmtTokens } from "./format"
import type { ChangeRequest, ExecutionMeta, FileChange } from "@/types"

describe("timeAgo", () => {
  it("returns empty for missing/invalid input", () => {
    expect(timeAgo(null)).toBe("")
    expect(timeAgo("not-a-date")).toBe("")
  })
  it("bucketizes recent times", () => {
    const now = Date.now()
    expect(timeAgo(new Date(now - 5_000).toISOString())).toBe("just now")
    expect(timeAgo(new Date(now - 5 * 60_000).toISOString())).toBe("5 min ago")
    expect(timeAgo(new Date(now - 3 * 3_600_000).toISOString())).toBe("3h ago")
    expect(timeAgo(new Date(now - 24 * 3_600_000).toISOString())).toBe("yesterday")
  })
})

describe("pageTags", () => {
  it("extracts unique wiki dirs", () => {
    const changes = [
      { path: "wiki/concepts/a.md" },
      { path: "wiki/concepts/b.md" },
      { path: "wiki/synthesis/c.md" },
      { path: "raw/x.md" },
    ] as FileChange[]
    expect(pageTags(changes).sort()).toEqual(["concepts", "synthesis"])
  })
})

describe("crKind", () => {
  it("labels by summary", () => {
    expect(crKind({ summary: "Saved answer: x" } as ChangeRequest)).toBe("ask --save")
    expect(crKind({ summary: "Delete page: x" } as ChangeRequest)).toBe("ingest")
    expect(crKind({ summary: "lint fixes" } as ChangeRequest)).toBe("maintain")
  })
})

describe("fmtTokens / execLine (#185)", () => {
  it("compacts thousands", () => {
    expect(fmtTokens(950)).toBe("950")
    expect(fmtTokens(12300)).toBe("12.3k")
  })
  it("renders the telemetry line, omitting zero latency/tools", () => {
    const e: ExecutionMeta = {
      model: "anthropic:claude",
      tokens_in: 12300,
      tokens_out: 2100,
      tool_calls: 7,
      latency_ms: 4500,
      used_fallback: false,
    }
    expect(execLine(e)).toBe("anthropic:claude · 12.3k in / 2.1k out · 4.5s · 7 tools")
    expect(execLine({ ...e, latency_ms: 0, tool_calls: 0 })).toBe(
      "anthropic:claude · 12.3k in / 2.1k out",
    )
  })
})
