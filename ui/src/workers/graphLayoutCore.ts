// Pure force-layout core (#194), shared by the Web Worker and unit tests.
//
// Kept free of any `self`/worker globals so it runs in node/vitest. The worker
// is a thin wrapper that streams `onTick` snapshots over postMessage.

import {
  forceCenter,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force"

interface SimNode extends SimulationNodeDatum {
  id: string
}
type SimLink = SimulationLinkDatum<SimNode>

export interface LayoutRequest {
  nodes: { id: string; x?: number; y?: number }[]
  edges: { source: string; target: string }[]
  width: number
  height: number
  /** Starting alpha — low (≈0.3) when most nodes have cached positions. */
  alpha: number
}

export type Positions = Record<string, [number, number]>

function snapshot(nodes: SimNode[]): Positions {
  const out: Positions = {}
  for (const n of nodes) out[n.id] = [n.x ?? 0, n.y ?? 0]
  return out
}

/**
 * Run the simulation to completion. `onTick` (if given) receives throttled
 * intermediate snapshots; the final positions are returned.
 */
export function runLayout(
  req: LayoutRequest,
  onTick?: (positions: Positions) => void,
): Positions {
  const { nodes, edges, width, height, alpha } = req
  const simNodes: SimNode[] = nodes.map((n) => ({ id: n.id, x: n.x, y: n.y }))
  const ids = new Set(simNodes.map((n) => n.id))
  const simLinks: SimLink[] = edges
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }))

  const sim: Simulation<SimNode, SimLink> = forceSimulation(simNodes)
    .force(
      "charge",
      forceManyBody<SimNode>().strength(-220).theta(0.9).distanceMax(600),
    )
    .force(
      "link",
      forceLink<SimNode, SimLink>(simLinks)
        .id((d) => d.id)
        .distance(70)
        .strength(0.4),
    )
    .force("center", forceCenter(width / 2, height / 2))
    .alpha(Math.max(0.05, Math.min(1, alpha)))
    .alphaMin(0.02)
    .stop()

  // Drive ticks ourselves so postMessage throttling is explicit and the worker
  // (not d3's timer) owns the loop — leaving the main thread free.
  let i = 0
  const maxTicks = 500
  while (sim.alpha() > sim.alphaMin() && i < maxTicks) {
    sim.tick()
    if (onTick && i % 6 === 0) onTick(snapshot(simNodes))
    i++
  }
  return snapshot(simNodes)
}
