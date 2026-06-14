// Unit tests for the pure viewport math (#252).

import { describe, it, expect } from "vitest"
import {
  boundsOf,
  clampZoom,
  fit,
  fitToBounds,
  MAX_ZOOM,
  MIN_ZOOM,
  panBy,
  screenToWorld,
  worldToScreen,
  zoomAt,
  type ScreenRect,
  type Viewport,
  type WorldRect,
} from "./graphViewport"

const world: WorldRect = { w: 1000, h: 700 }
const screen: ScreenRect = { w: 1000, h: 700 }
const zero: Viewport = { x: 0, y: 0, zoom: 1 }

describe("clampZoom", () => {
  it("returns the value inside the range", () => {
    expect(clampZoom(1)).toBe(1)
    expect(clampZoom(0.5)).toBe(0.5)
    expect(clampZoom(2)).toBe(2)
  })
  it("clamps below MIN_ZOOM", () => {
    expect(clampZoom(0.01)).toBe(MIN_ZOOM)
    expect(clampZoom(-3)).toBe(MIN_ZOOM)
  })
  it("clamps above MAX_ZOOM", () => {
    expect(clampZoom(99)).toBe(MAX_ZOOM)
  })
  it("rejects NaN / Infinity", () => {
    expect(clampZoom(NaN)).toBe(1)
    expect(clampZoom(Infinity)).toBe(MAX_ZOOM)
  })
})

describe("fit", () => {
  it("centres a 1:1 world in a 1:1 screen", () => {
    const r = fit({ w: 100, h: 100 }, { w: 200, h: 200 })
    expect(r.scale).toBe(2)
    expect(r.ox).toBe(0)
    expect(r.oy).toBe(0)
  })
  it("uses the smaller ratio and centres on the other axis", () => {
    const r = fit({ w: 100, h: 200 }, { w: 200, h: 100 })
    // width ratio 2, height ratio 0.5 → use 0.5
    expect(r.scale).toBe(0.5)
    expect(r.ox).toBe(75)
    expect(r.oy).toBe(0)
  })
})

describe("screenToWorld / worldToScreen (round-trip)", () => {
  it("identity at zoom=1, no pan", () => {
    for (const [x, y] of [[10, 10], [500, 350], [990, 690]]) {
      const w = screenToWorld(zero, screen, world, x, y)
      expect(worldToScreen(zero, screen, world, w.x, w.y)).toEqual({ x, y })
    }
  })
  it("pan shifts the world origin in the opposite direction", () => {
    const v: Viewport = { x: 50, y: 0, zoom: 1 }
    const w = screenToWorld(v, screen, world, 500, 350)
    // Origin moved by 50 → world x is offset by 50
    expect(w.x).toBeCloseTo(450)
  })
})

describe("zoomAt", () => {
  it("keeps the anchor world-point under the cursor after zooming", () => {
    const anchor = { x: 500, y: 350 }
    const before = screenToWorld(zero, screen, world, anchor.x, anchor.y)
    const v2 = zoomAt(zero, screen, world, anchor, 2)
    const after = screenToWorld(v2, screen, world, anchor.x, anchor.y)
    expect(after.x).toBeCloseTo(before.x, 3)
    expect(after.y).toBeCloseTo(before.y, 3)
  })
  it("clamps to MIN_ZOOM and MAX_ZOOM", () => {
    const v = zoomAt(zero, screen, world, { x: 0, y: 0 }, 1000)
    expect(v.zoom).toBe(MAX_ZOOM)
    const v2 = zoomAt(v, screen, world, { x: 0, y: 0 }, 0.0001)
    expect(v2.zoom).toBe(MIN_ZOOM)
  })
  it("returns the same viewport when zoom is already clamped", () => {
    const v = { x: 1, y: 2, zoom: MAX_ZOOM }
    const r = zoomAt(v, screen, world, { x: 0, y: 0 }, 2)
    expect(r).toBe(v)
  })
})

describe("fitToBounds", () => {
  it("zooms to make a small cluster fill the screen", () => {
    const bounds = { minX: 400, minY: 300, maxX: 600, maxY: 400 } // 200x100
    const v = fitToBounds(zero, screen, world, bounds, 0)
    // After fit, the cluster's centre should be at the screen centre
    const centre = worldToScreen(v, screen, world, 500, 350)
    expect(centre.x).toBeCloseTo(500, 0)
    expect(centre.y).toBeCloseTo(350, 0)
    expect(v.zoom).toBeGreaterThan(1)
  })
  it("returns the viewport unchanged for null bounds", () => {
    expect(fitToBounds(zero, screen, world, null)).toBe(zero)
  })
  it("respects padding", () => {
    const tight = fitToBounds(zero, screen, world, { minX: 0, minY: 0, maxX: 1000, maxY: 700 }, 0)
    const padded = fitToBounds(zero, screen, world, { minX: 0, minY: 0, maxX: 1000, maxY: 700 }, 0.2)
    expect(padded.zoom).toBeLessThan(tight.zoom)
  })
})

describe("boundsOf", () => {
  it("returns null for empty input", () => {
    expect(boundsOf([])).toBeNull()
  })
  it("computes the axis-aligned bounding box", () => {
    expect(
      boundsOf([
        { x: 1, y: 2 },
        { x: -3, y: 4 },
        { x: 5, y: 0 },
      ]),
    ).toEqual({ minX: -3, minY: 0, maxX: 5, maxY: 4 })
  })
})

describe("panBy", () => {
  it("translates the viewport by screen-pixel deltas, scaled by zoom", () => {
    const v = panBy(zero, world, screen, 100, 0)
    // scale=1, zoom=1 → world units
    expect(v.x).toBeCloseTo(100)
    // with 2x zoom the same screen delta is half the world delta
    const v2 = panBy({ x: 0, y: 0, zoom: 2 }, world, screen, 100, 0)
    expect(v2.x).toBeCloseTo(50)
  })
})
