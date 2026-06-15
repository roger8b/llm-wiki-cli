// Per-brain cache of graph node positions (#194).
//
// Persisting the laid-out positions in localStorage lets the graph reopen with
// a stable layout (cached nodes start where they were, low simulation alpha)
// instead of re-exploding from a fresh circle every time.

export type Positions = Record<string, [number, number]>

const PREFIX = "graph-pos:"

function store(): Storage | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null
  } catch {
    // Access can throw in sandboxed iframes / SSR — degrade to no cache.
    return null
  }
}

function keyFor(brainId: string | null | undefined): string {
  return `${PREFIX}${brainId ?? "default"}`
}

/** Load cached positions for a brain; `{}` when absent or unparsable. */
export function loadPositions(brainId: string | null | undefined): Positions {
  const s = store()
  if (!s) return {}
  try {
    const raw = s.getItem(keyFor(brainId))
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return {}
    const out: Positions = {}
    for (const [path, xy] of Object.entries(parsed as Record<string, unknown>)) {
      if (
        Array.isArray(xy) &&
        xy.length === 2 &&
        typeof xy[0] === "number" &&
        typeof xy[1] === "number"
      ) {
        out[path] = [xy[0], xy[1]]
      }
    }
    return out
  } catch {
    return {}
  }
}

/** Persist positions for a brain (best-effort; quota/SSR errors are ignored). */
export function savePositions(
  brainId: string | null | undefined,
  positions: Positions,
): void {
  const s = store()
  if (!s) return
  try {
    s.setItem(keyFor(brainId), JSON.stringify(positions))
  } catch {
    // Quota exceeded or storage disabled — the cache is an optimisation only.
  }
}
