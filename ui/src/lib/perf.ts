// Pure helpers for the "Performance da ingestão" card (#280). Parse a job's
// persisted result (durations_ms + execution, from #276) into a renderable
// per-step breakdown. No DOM here so this is unit-testable in isolation.

/** Human labels for pipeline steps; chunk passes are handled dynamically. */
const STEP_LABELS: Record<string, string> = {
  extracting: "Reading source",
  outlining: "Planning concepts",
  running_agent: "Agent reading & writing",
  fixing_structural_issues: "Fixing structure",
  creating_change_request: "Preparing change request",
}

export function stepLabel(name: string): string {
  if (STEP_LABELS[name]) return STEP_LABELS[name]
  const chunk = /^chunk (\d+)\/(\d+)$/.exec(name)
  if (chunk) return `Chunk ${chunk[1]}/${chunk[2]}`
  return name
}

/** Compact duration: "340ms", "1.2s", "2m 05s". */
export function formatMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—"
  if (ms < 1000) return `${Math.round(ms)}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  return `${m}m ${String(Math.round(s % 60)).padStart(2, "0")}s`
}

export interface PerfSegment {
  name: string
  label: string
  ms: number
  pct: number
}

export interface IngestionPerf {
  segments: PerfSegment[]
  totalMs: number
  tokensIn: number | null
  tokensOut: number | null
  toolCalls: number | null
  invokes: number | null
  model: string | null
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

/**
 * Parse a job's ``result`` JSON string into a performance breakdown, or null
 * when there is no per-step timing to show. Preserves the persisted step order
 * (the pipeline order), so the stacked bar reads extract → outline → chunks →
 * fix → CR.
 */
export function parsePerf(result: string | null | undefined): IngestionPerf | null {
  if (!result) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(result)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== "object") return null
  const obj = parsed as Record<string, unknown>
  const durations = obj.durations_ms
  if (!durations || typeof durations !== "object") return null

  const entries = Object.entries(durations as Record<string, unknown>)
    .map(([name, v]) => [name, num(v) ?? 0] as const)
    .filter(([, ms]) => ms >= 0)
  if (entries.length === 0) return null

  const totalMs = entries.reduce((sum, [, ms]) => sum + ms, 0)
  const segments: PerfSegment[] = entries.map(([name, ms]) => ({
    name,
    label: stepLabel(name),
    ms,
    pct: totalMs > 0 ? (ms / totalMs) * 100 : 0,
  }))

  const exec = (obj.execution ?? null) as Record<string, unknown> | null
  return {
    segments,
    totalMs,
    tokensIn: exec ? num(exec.tokens_in) : null,
    tokensOut: exec ? num(exec.tokens_out) : null,
    toolCalls: exec ? num(exec.tool_calls) : null,
    invokes: exec ? num(exec.invokes) ?? num(exec.passes) : null,
    model: exec && typeof exec.model === "string" ? exec.model : null,
  }
}
