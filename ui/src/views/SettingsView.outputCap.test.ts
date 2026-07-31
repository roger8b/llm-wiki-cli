import { describe, it, expect } from "vitest"
import { parseCaps } from "./SettingsView"

// "No cap" is expressed by the key being absent, never by 0 — the backend
// rejects a non-positive cap on write (#370). So an empty field clears, but a
// non-empty invalid one must block the save instead of being dropped, which
// would wipe the stored cap while reporting success.
describe("parseCaps (#370)", () => {
  it("keeps positive numbers", () => {
    expect(parseCaps({ ingest: "2048", ask: "512" })).toEqual({
      values: { ingest: 2048, ask: 512 },
      errors: [],
    })
  })

  it("treats a cleared field as 'no cap', with no error", () => {
    expect(parseCaps({ ingest: "", ask: "   " })).toEqual({ values: {}, errors: [] })
  })

  it("reports non-positive and non-numeric values instead of dropping them", () => {
    const { values, errors } = parseCaps({ a: "0", b: "-5", c: "abc" })
    expect(values).toEqual({})
    expect(errors).toHaveLength(3)
    expect(errors[0]).toContain("a")
  })

  it("does not let an invalid field clear a valid sibling", () => {
    const { values, errors } = parseCaps({ ingest: "2048", ask: "0" })
    expect(values).toEqual({ ingest: 2048 })
    expect(errors).toHaveLength(1)
  })

  it("clearing one op leaves the others untouched", () => {
    expect(parseCaps({ ingest: "2048", ask: "" })).toEqual({
      values: { ingest: 2048 },
      errors: [],
    })
  })
})
