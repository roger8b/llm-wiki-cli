import { describe, expect, it } from "vitest"
import { truncateBatchItems } from "./batchItems"

describe("truncateBatchItems (#339)", () => {
  it("returns all items when count is at or below the limit", () => {
    const items = Array.from({ length: 20 }, (_, i) => `f${i}.md`)
    const { visible, hiddenCount } = truncateBatchItems(items, 20)
    expect(visible).toHaveLength(20)
    expect(hiddenCount).toBe(0)
  })

  it("collapses items past the limit and reports the hidden count", () => {
    const items = Array.from({ length: 35 }, (_, i) => `f${i}.md`)
    const { visible, hiddenCount } = truncateBatchItems(items, 20)
    expect(visible).toHaveLength(20)
    expect(hiddenCount).toBe(15)
  })

  it("returns the original array reference when nothing is hidden", () => {
    const items = ["a", "b", "c"]
    const { visible } = truncateBatchItems(items, 20)
    expect(visible).toBe(items)
  })

  it("returns empty result for an empty list", () => {
    const { visible, hiddenCount } = truncateBatchItems([], 20)
    expect(visible).toEqual([])
    expect(hiddenCount).toBe(0)
  })
})