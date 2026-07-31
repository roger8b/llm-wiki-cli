import { describe, it, expect } from "vitest"
import { capsToPatch } from "./SettingsView"

// The backend rejects a non-positive cap on write (#370), and "no cap" is
// expressed by the key being absent — never by 0. The form keeps the inputs as
// strings, so this is where an empty/invalid field must be dropped.
describe("capsToPatch (#370)", () => {
  it("keeps positive numbers", () => {
    expect(capsToPatch({ ingest: "2048", ask: "512" })).toEqual({ ingest: 2048, ask: 512 })
  })

  it("drops cleared fields instead of sending 0", () => {
    expect(capsToPatch({ ingest: "", ask: "   " })).toEqual({})
  })

  it("drops non-positive and non-numeric values", () => {
    expect(capsToPatch({ a: "0", b: "-5", c: "abc" })).toEqual({})
  })

  it("clearing one op leaves the others untouched", () => {
    expect(capsToPatch({ ingest: "2048", ask: "" })).toEqual({ ingest: 2048 })
  })
})
