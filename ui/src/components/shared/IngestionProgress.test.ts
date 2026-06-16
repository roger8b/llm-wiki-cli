import { describe, it, expect } from "vitest"
import { foldSteps, estimateEtaMs } from "./IngestionProgress"
import type { IngestEvent } from "@/types"

function ev(id: number, kind: IngestEvent["kind"], payload: IngestEvent["payload"]): IngestEvent {
  return { id, kind, ts: "t", payload }
}

describe("foldSteps", () => {
  it("folds start/end into ordered steps with durations", () => {
    const steps = foldSteps([
      ev(1, "step", { name: "extracting", status: "start" }),
      ev(2, "step", { name: "extracting", status: "end", duration_ms: 120 }),
      ev(3, "step", { name: "running_agent", status: "start" }),
      ev(4, "page_write", { path: "x" }), // ignored
    ])
    expect(steps.map((s) => s.name)).toEqual(["extracting", "running_agent"])
    expect(steps[0]).toMatchObject({ done: true, durationMs: 120 })
    expect(steps[1]).toMatchObject({ done: false })
  })
})

describe("estimateEtaMs", () => {
  it("projects remaining chunks from the average finished duration", () => {
    // 1 of 3 chunks finished in 1000ms → ~2000ms left for the other two.
    const eta = estimateEtaMs([
      ev(1, "step", { name: "chunk 1/3", status: "start" }),
      ev(2, "step", { name: "chunk 1/3", status: "end", duration_ms: 1000 }),
      ev(3, "step", { name: "chunk 2/3", status: "start" }),
    ])
    expect(eta).toBe(2000)
  })

  it("returns null when no chunk has finished", () => {
    expect(estimateEtaMs([ev(1, "step", { name: "extracting", status: "start" })])).toBeNull()
  })
})
