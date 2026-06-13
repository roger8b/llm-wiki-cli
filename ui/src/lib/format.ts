import type { ChangeRequest, ExecutionMeta, FileChange } from "@/types"

/** Compact token count, e.g. 12300 → "12.3k" (#185). */
export function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`
}

/** Discreet CR telemetry line: "model · 12.3k in / 2.1k out · 4.5s · 7 tools". */
export function execLine(e: ExecutionMeta): string {
  const parts = [e.model, `${fmtTokens(e.tokens_in)} in / ${fmtTokens(e.tokens_out)} out`]
  if (e.latency_ms) parts.push(`${(e.latency_ms / 1000).toFixed(1)}s`)
  if (e.tool_calls) parts.push(`${e.tool_calls} tools`)
  return parts.join(" · ")
}

/** Compact relative time, e.g. "2 min ago", "3h ago", "yesterday". */
export function timeAgo(iso?: string | null): string {
  if (!iso) return ""
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const secs = Math.floor((Date.now() - then) / 1000)
  if (secs < 60) return "just now"
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return "yesterday"
  if (days < 7) return `${days} days ago`
  return new Date(iso).toLocaleDateString()
}

/** Unique wiki page-type directories touched by a CR (concepts, synthesis…). */
export function pageTags(changes: FileChange[]): string[] {
  const tags = new Set<string>()
  for (const c of changes) {
    const m = /^wiki\/([^/]+)\//.exec(c.path)
    if (m) tags.add(m[1])
  }
  return [...tags]
}

/** Best-effort label for what produced the CR. */
export function crKind(cr: ChangeRequest): string {
  if (/answer/i.test(cr.summary)) return "ask --save"
  if (/lint|fix|merge/i.test(cr.summary)) return "maintain"
  return "ingest"
}
