import { afterEach, describe, expect, it } from "vitest"
import { useAppStore } from "./app"

describe("useAppStore.setPendingSourceCount (#340)", () => {
  afterEach(() => {
    // Reset between tests so the count doesn't leak.
    useAppStore.getState().setPendingSourceCount(0)
  })

  it("defaults pendingSourceCount to 0 on cold start", () => {
    useAppStore.setState({ pendingSourceCount: 0 })
    expect(useAppStore.getState().pendingSourceCount).toBe(0)
  })

  it("updates pendingSourceCount when the setter is called", () => {
    useAppStore.getState().setPendingSourceCount(7)
    expect(useAppStore.getState().pendingSourceCount).toBe(7)
  })

  it("is independent of pendingCount (Review's count) — zeroing one does not touch the other", () => {
    useAppStore.getState().setPendingCount(3)
    useAppStore.getState().setPendingSourceCount(5)
    expect(useAppStore.getState().pendingCount).toBe(3)
    expect(useAppStore.getState().pendingSourceCount).toBe(5)
    useAppStore.getState().setPendingSourceCount(0)
    expect(useAppStore.getState().pendingCount).toBe(3)
    expect(useAppStore.getState().pendingSourceCount).toBe(0)
  })
})