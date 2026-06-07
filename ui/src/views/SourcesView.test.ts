import { describe, expect, it } from "vitest"
import type { Source } from "@/types"
import { groupBySourceDir } from "./SourcesView"

function src(path: string): Source {
  return {
    path,
    type: "md",
    hash: "abcdef0123",
    added_at: "2026-06-07T00:00:00Z",
    status: "pending",
  }
}

describe("groupBySourceDir", () => {
  it("groups by the raw/ subdirectory", () => {
    const groups = groupBySourceDir([
      src("raw/articles/a.md"),
      src("raw/articles/b.md"),
      src("raw/notes/c.md"),
    ])
    expect(Object.keys(groups).sort()).toEqual(["articles", "notes"])
    expect(groups.articles).toHaveLength(2)
    expect(groups.notes).toHaveLength(1)
  })

  it("puts top-level raw files under 'raw'", () => {
    const groups = groupBySourceDir([src("raw/x.md")])
    expect(groups.raw).toHaveLength(1)
  })
})
