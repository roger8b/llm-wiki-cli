import { describe, it, expect } from "vitest"
import { timeAgo, pageTags, crKind } from "./format"
import type { ChangeRequest, FileChange } from "@/types"

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
