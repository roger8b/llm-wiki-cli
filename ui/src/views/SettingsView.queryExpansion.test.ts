import { describe, it, expect } from "vitest"
import { normalizeExpansion } from "./SettingsView"

// Only 0/2/3 were measured (#355). Anything else — including a hand-written
// value or a missing key from an older backend — must render as "off", which is
// how the backend behaves for <= 0.
describe("normalizeExpansion (#371)", () => {
  it("keeps the measured levels", () => {
    expect(normalizeExpansion(0)).toBe(0)
    expect(normalizeExpansion(2)).toBe(2)
    expect(normalizeExpansion(3)).toBe(3)
  })

  it("falls back to off for unmeasured, negative or missing values", () => {
    expect(normalizeExpansion(1)).toBe(0)
    expect(normalizeExpansion(7)).toBe(0)
    expect(normalizeExpansion(-2)).toBe(0)
    expect(normalizeExpansion(undefined)).toBe(0)
    expect(normalizeExpansion(null)).toBe(0)
  })
})
