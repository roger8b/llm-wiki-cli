import { beforeEach, describe, expect, it, vi } from "vitest"
import { loadPositions, savePositions } from "./graphPositions"

// jsdom in this vitest setup ships without Web Storage — install a minimal shim.
beforeEach(() => {
  const store = new Map<string, string>()
  const shim: Storage = {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (k) => store.get(k) ?? null,
    key: (i) => [...store.keys()][i] ?? null,
    removeItem: (k) => store.delete(k),
    setItem: (k, v) => void store.set(k, String(v)),
  }
  vi.stubGlobal("localStorage", shim)
})

describe("graphPositions cache", () => {
  beforeEach(() => localStorage.clear())

  it("round-trips positions per brain", () => {
    savePositions("brain-a", { "wiki/x.md": [10, 20], "wiki/y.md": [30, 40] })
    expect(loadPositions("brain-a")).toEqual({
      "wiki/x.md": [10, 20],
      "wiki/y.md": [30, 40],
    })
  })

  it("isolates positions by brain id", () => {
    savePositions("brain-a", { "wiki/x.md": [1, 2] })
    savePositions("brain-b", { "wiki/x.md": [9, 9] })
    expect(loadPositions("brain-a")["wiki/x.md"]).toEqual([1, 2])
    expect(loadPositions("brain-b")["wiki/x.md"]).toEqual([9, 9])
  })

  it("returns {} for an unknown brain", () => {
    expect(loadPositions("nope")).toEqual({})
  })

  it("falls back to a default key when brainId is null", () => {
    savePositions(null, { "wiki/x.md": [5, 6] })
    expect(loadPositions(null)).toEqual({ "wiki/x.md": [5, 6] })
  })

  it("drops malformed entries instead of throwing", () => {
    localStorage.setItem(
      "graph-pos:brain-a",
      JSON.stringify({ good: [1, 2], bad: "x", short: [1], wrong: [1, "y"] }),
    )
    expect(loadPositions("brain-a")).toEqual({ good: [1, 2] })
  })

  it("returns {} on invalid JSON", () => {
    localStorage.setItem("graph-pos:brain-a", "{not json")
    expect(loadPositions("brain-a")).toEqual({})
  })
})
