/// <reference lib="webworker" />
// d3-force layout off the main thread (#194). Thin wrapper around the pure
// `runLayout` core: receives the graph once, streams throttled position
// snapshots back, then a final `done` — keeping the main thread free.

import { runLayout, type LayoutRequest, type Positions } from "./graphLayoutCore"

export type { LayoutRequest } from "./graphLayoutCore"

export type LayoutResponse =
  | { type: "tick"; positions: Positions }
  | { type: "done"; positions: Positions }

const ctx = self as unknown as DedicatedWorkerGlobalScope

ctx.onmessage = (e: MessageEvent<LayoutRequest>) => {
  const positions = runLayout(e.data, (snapshot) => {
    ctx.postMessage({ type: "tick", positions: snapshot })
  })
  ctx.postMessage({ type: "done", positions })
}
