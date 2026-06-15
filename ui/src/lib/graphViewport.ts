// Pure viewport math for the graph view (#252).
//
// The "world" is the laid-out coordinate system (the simulation output). The
// "screen" is the rendered surface — the SVG `viewBox` rect or the canvas's
// CSS-pixel rect. The viewport maps world → screen:
//
//   screen.x = (world.x + viewport.x) * viewport.zoom * scale + offsetX
//   screen.y = (world.y + viewport.y) * viewport.zoom * scale + offsetY
//
// where `scale = min(rect.w/world.w, rect.h/world.h)` keeps the world aspect
// inside the screen rect, and `(offsetX, offsetY)` centres it.
//
// All functions in this module are pure so they're trivially unit-testable
// (`graphViewport.test.ts`).

export interface Viewport {
  x: number
  y: number
  zoom: number
}

export interface WorldRect {
  w: number
  h: number
}

export interface ScreenRect {
  w: number
  h: number
}

/** Clamp a zoom factor into the supported range. */
export const MIN_ZOOM = 0.1
export const MAX_ZOOM = 5

export function clampZoom(zoom: number): number {
  if (Number.isNaN(zoom)) return 1
  if (zoom === Infinity) return MAX_ZOOM
  if (zoom === -Infinity) return MIN_ZOOM
  if (zoom > MAX_ZOOM) return MAX_ZOOM
  if (zoom < MIN_ZOOM) return MIN_ZOOM
  return zoom
}

/** Fit a viewport's world inside a screen rect (uniform scale, centred). */
export function fit(
  world: WorldRect,
  screen: ScreenRect,
): { scale: number; ox: number; oy: number } {
  const scale = Math.min(screen.w / world.w, screen.h / world.h)
  const ox = (screen.w - world.w * scale) / 2
  const oy = (screen.h - world.h * scale) / 2
  return { scale, ox, oy }
}

/** Convert a screen-space point to world coordinates, given the viewport. */
export function screenToWorld(
  viewport: Viewport,
  screen: ScreenRect,
  world: WorldRect,
  sx: number,
  sy: number,
): { x: number; y: number } {
  const { scale, ox, oy } = fit(world, screen)
  return {
    x: (sx - ox) / (scale * viewport.zoom) - viewport.x,
    y: (sy - oy) / (scale * viewport.zoom) - viewport.y,
  }
}

/** Convert a world-space point to screen coordinates, given the viewport. */
export function worldToScreen(
  viewport: Viewport,
  screen: ScreenRect,
  world: WorldRect,
  wx: number,
  wy: number,
): { x: number; y: number } {
  const { scale, ox, oy } = fit(world, screen)
  return {
    x: (wx + viewport.x) * scale * viewport.zoom + ox,
    y: (wy + viewport.y) * scale * viewport.zoom + oy,
  }
}

/**
 * Zoom the viewport around a screen-space anchor (e.g. cursor position) so
 * the world point currently under the cursor stays under it after the zoom.
 *
 * `factor` is multiplicative (>1 zooms in, <1 zooms out). The result is
 * clamped into `[MIN_ZOOM, MAX_ZOOM]`.
 */
export function zoomAt(
  viewport: Viewport,
  screen: ScreenRect,
  world: WorldRect,
  anchor: { x: number; y: number },
  factor: number,
): Viewport {
  const before = screenToWorld(viewport, screen, world, anchor.x, anchor.y)
  const zoom = clampZoom(viewport.zoom * factor)
  if (zoom === viewport.zoom) return viewport
  const { scale, ox, oy } = fit(world, screen)
  // screenToWorld(v, anchor) == before means:
  //   (anchor.x - ox) / (scale * zoom) - v.x = before.x
  //   v.x = (anchor.x - ox) / (scale * zoom) - before.x
  const vx = (anchor.x - ox) / (scale * zoom) - before.x
  const vy = (anchor.y - oy) / (scale * zoom) - before.y
  return { x: vx, y: vy, zoom }
}

/**
 * Adjust the viewport so the given world-space bounds fit inside the screen
 * rect (with `padding` fraction of margin on each side, default 10%). Returns
 * the unchanged viewport when `bounds` is empty.
 */
export function fitToBounds(
  viewport: Viewport,
  screen: ScreenRect,
  world: WorldRect,
  bounds: { minX: number; minY: number; maxX: number; maxY: number } | null,
  padding = 0.1,
): Viewport {
  if (!bounds) return viewport
  const bw = Math.max(1e-6, bounds.maxX - bounds.minX)
  const bh = Math.max(1e-6, bounds.maxY - bounds.minY)
  const availW = screen.w * (1 - 2 * padding)
  const availH = screen.h * (1 - 2 * padding)
  // The base fit() scale maps the *world rect* to the screen rect. We want
  // the bounds to fill the available area, so we need a per-axis scale.
  // The zoom is the multiplier that, applied to the base scale, makes the
  // bounds fit: base_scale * zoom * bw = availW  →  zoom = availW / (bw * base_scale).
  const baseScale = fit(world, screen).scale
  const zoom = clampZoom(
    Math.min(availW / (bw * baseScale), availH / (bh * baseScale)),
  )
  // Place the bounds' centre at the screen centre.
  const { ox, oy } = fit(world, screen)
  const cx = (bounds.minX + bounds.maxX) / 2
  const cy = (bounds.minY + bounds.maxY) / 2
  // (cx + vx) * baseScale * zoom + ox = screen.w / 2
  const vx = (screen.w / 2 - ox) / (baseScale * zoom) - cx
  const vy = (screen.h / 2 - oy) / (baseScale * zoom) - cy
  return { x: vx, y: vy, zoom }
}

/** Compute the world-space bounding box of a list of nodes. Null when empty. */
export function boundsOf(
  points: ReadonlyArray<{ x: number; y: number }>,
): { minX: number; minY: number; maxX: number; maxY: number } | null {
  if (points.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const p of points) {
    if (p.x < minX) minX = p.x
    if (p.y < minY) minY = p.y
    if (p.x > maxX) maxX = p.x
    if (p.y > maxY) maxY = p.y
  }
  return { minX, minY, maxX, maxY }
}

/** Apply a relative pan in screen pixels (e.g. from a drag gesture). */
export function panBy(
  viewport: Viewport,
  world: WorldRect,
  screen: ScreenRect,
  dx: number,
  dy: number,
): Viewport {
  const { scale } = fit(world, screen)
  return {
    ...viewport,
    x: viewport.x + dx / (scale * viewport.zoom),
    y: viewport.y + dy / (scale * viewport.zoom),
  }
}
