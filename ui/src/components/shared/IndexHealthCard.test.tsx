import { describe, it, expect } from "vitest"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { IndexHealthCard, formatIndexDrift, formatLastReindex } from "./IndexHealthCard"
import type { IndexStatus } from "@/types"

function render(status: IndexStatus | null, props: { busy?: boolean } = {}) {
  return renderToStaticMarkup(
    createElement(IndexHealthCard, { status, ...props }),
  )
}

const STALE_OK: IndexStatus = {
  db_pages: 178,
  disk_files: 178,
  drift: 0,
  stale: false,
  embeddings: { count: 178, expected: 178, enabled: true },
  last_reindex_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
}

const STALE_DRIFT: IndexStatus = {
  db_pages: 0,
  disk_files: 178,
  drift: 178,
  stale: true,
  embeddings: { count: 0, expected: 0, enabled: false },
  last_reindex_at: null,
}

const STALE_PARTIAL_EMB: IndexStatus = {
  db_pages: 10,
  disk_files: 10,
  drift: 0,
  stale: false,
  embeddings: { count: 3, expected: 10, enabled: true },
  last_reindex_at: "2026-06-20T00:00:00Z",
}

describe("formatIndexDrift (#306)", () => {
  it("signs positive drift and renders zero plainly", () => {
    expect(formatIndexDrift(178)).toBe("+178")
    expect(formatIndexDrift(0)).toBe("0")
    expect(formatIndexDrift(-3)).toBe("-3")
  })
})

describe("formatLastReindex (#306)", () => {
  const NOW = new Date("2026-06-26T12:00:00Z")

  it("renders a null timestamp as 'never'", () => {
    expect(formatLastReindex(null, NOW)).toBe("never")
  })

  it("renders minutes ago for recent runs", () => {
    const iso = new Date(NOW.getTime() - 5 * 60 * 1000).toISOString()
    expect(formatLastReindex(iso, NOW)).toBe("5 min ago")
  })

  it("renders hours ago for older runs", () => {
    const iso = new Date(NOW.getTime() - 3 * 60 * 60 * 1000).toISOString()
    expect(formatLastReindex(iso, NOW)).toBe("3h ago")
  })

  it("renders days ago for very old runs", () => {
    const iso = new Date(NOW.getTime() - 6 * 24 * 60 * 60 * 1000).toISOString()
    expect(formatLastReindex(iso, NOW)).toBe("6d ago")
  })
})

describe("IndexHealthCard render (#306)", () => {
  it("renders the loading skeleton when status is null", () => {
    const html = render(null)
    expect(html).toContain("Index health")
    expect(html).toContain("Loading")
  })

  it("renders drift and embeddings for a fresh index (no warning)", () => {
    const html = render(STALE_OK)
    expect(html).toContain("Index health")
    expect(html).toContain("178")
    expect(html).toContain("178 / 178")
    // embeddings enabled → shows count/expected, not "Disabled"
    expect(html).toContain("178 / 178")
    expect(html).not.toContain("Disabled")
    // drift=0 → no warning surface
    expect(html).not.toContain("Stale")
  })

  it("highlights stale state with a warning when drift != 0", () => {
    const html = render(STALE_DRIFT)
    expect(html).toContain("Stale")
    expect(html).toContain("+178")
  })

  it("renders embeddings as disabled when no embedding_model is configured (#no-error)", () => {
    const html = render(STALE_DRIFT)
    // enabled=false → "Disabled" label, not a thrown error
    expect(html).toContain("Disabled")
    expect(html).not.toContain("0/0") // we don't show the fraction when disabled
  })

  it("renders partial embeddings (count < expected) without crashing", () => {
    const html = render(STALE_PARTIAL_EMB)
    expect(html).toContain("3 / 10")
  })

  it("renders a Reindex button that is disabled while a job is busy", () => {
    const html = render(STALE_DRIFT, { busy: true })
    expect(html).toContain("Reindex")
    expect(html).toContain("disabled")
  })

  it("renders a Reindex button that is enabled when idle", () => {
    const html = render(STALE_DRIFT, { busy: false })
    expect(html).toContain("Reindex")
    // The button itself must NOT be disabled when no job is running.
    expect(html).toMatch(/<button[^>]*data-testid="reindex-button"[^>]*>/)
  })
})