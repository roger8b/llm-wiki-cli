import { describe, expect, it } from "vitest"
import type { Source } from "@/types"
import {
  countByStatus,
  groupBySourceDir,
  statusDotClass,
  statusDotLabel,
} from "./SourcesView"

function src(path: string, status: Source["status"] = "pending"): Source {
  return {
    path,
    type: "md",
    hash: "abcdef0123",
    added_at: "2026-06-07T00:00:00Z",
    status,
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

describe("statusDotClass (#336)", () => {
  it("uses bg-apply for processed (matches statusBadge palette)", () => {
    expect(statusDotClass("processed")).toContain("bg-apply")
  })

  it("uses bg-pending for pending", () => {
    expect(statusDotClass("pending")).toContain("bg-pending")
  })

  it("uses bg-primary and animate-pulse for processing (live signal)", () => {
    const cls = statusDotClass("processing")
    expect(cls).toContain("bg-primary")
    expect(cls).toContain("animate-pulse")
  })

  it("uses bg-rejected for error", () => {
    expect(statusDotClass("error")).toContain("bg-rejected")
  })

  it("always renders a circular 6px dot regardless of status", () => {
    for (const s of ["processed", "pending", "processing", "error"] as const) {
      const cls = statusDotClass(s)
      expect(cls).toContain("rounded-full")
      expect(cls).toContain("size-1.5")
    }
  })
})

describe("statusDotLabel (#336)", () => {
  it("returns a human-readable label per status for tooltip + aria-label", () => {
    expect(statusDotLabel("processed")).toBe("Ingested")
    expect(statusDotLabel("pending")).toBe("Pending ingest")
    expect(statusDotLabel("processing")).toMatch(/processing/i)
    expect(statusDotLabel("error")).toMatch(/fail/i)
  })
})

describe("countByStatus (#337)", () => {
  it("returns zeros for an empty list", () => {
    expect(countByStatus([])).toEqual({ total: 0, pending: 0, processed: 0 })
  })

  it("splits a mix of processed and pending correctly", () => {
    const items = [
      src("raw/articles/a.md", "processed"),
      src("raw/articles/b.md", "pending"),
      src("raw/articles/c.md", "pending"),
    ]
    expect(countByStatus(items)).toEqual({ total: 3, pending: 2, processed: 1 })
  })

  it("counts processing and error as pending (AC5 edge case)", () => {
    const items = [
      src("raw/articles/a.md", "processing"),
      src("raw/articles/b.md", "error"),
      src("raw/articles/c.md", "error"),
    ]
    // All 3 are non-processed → all 3 counted as pending
    expect(countByStatus(items)).toEqual({ total: 3, pending: 3, processed: 0 })
  })

  it("returns pending=0 when every item is processed", () => {
    const items = [
      src("raw/articles/a.md", "processed"),
      src("raw/articles/b.md", "processed"),
    ]
    expect(countByStatus(items)).toEqual({ total: 2, pending: 0, processed: 2 })
  })
})
