import { describe, expect, it, vi } from "vitest"
import { runLayout, type LayoutRequest } from "./graphLayoutCore"

const REQ: LayoutRequest = {
  nodes: [{ id: "a" }, { id: "b" }, { id: "c" }],
  edges: [
    { source: "a", target: "b" },
    { source: "b", target: "c" },
  ],
  width: 1000,
  height: 700,
  alpha: 1,
}

describe("runLayout (worker core)", () => {
  it("returns finite positions keyed by every node id", () => {
    const pos = runLayout(REQ)
    expect(Object.keys(pos).sort()).toEqual(["a", "b", "c"])
    for (const [x, y] of Object.values(pos)) {
      expect(Number.isFinite(x)).toBe(true)
      expect(Number.isFinite(y)).toBe(true)
    }
  })

  it("emits intermediate tick snapshots before the final result", () => {
    const onTick = vi.fn()
    runLayout(REQ, onTick)
    expect(onTick).toHaveBeenCalled()
    const last = onTick.mock.calls.at(-1)![0]
    expect(Object.keys(last).sort()).toEqual(["a", "b", "c"])
  })

  it("ignores edges that reference unknown nodes", () => {
    const pos = runLayout({
      ...REQ,
      edges: [{ source: "a", target: "ghost" }],
    })
    expect(Object.keys(pos)).toContain("a")
    expect(pos.ghost).toBeUndefined()
  })

  it("connected nodes settle closer than the canvas span", () => {
    const pos = runLayout(REQ)
    const [ax, ay] = pos.a
    const [bx, by] = pos.b
    const dist = Math.hypot(ax - bx, ay - by)
    expect(dist).toBeLessThan(400) // linked a–b pulled together, not flung apart
  })
})
