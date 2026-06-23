import { useMemo } from "react"
import { parsePerf, formatMs } from "@/lib/perf"

// Stable-ish palette for the stacked bar; steps cycle through it in pipeline
// order. Tailwind class strings (must be literal so the JIT keeps them).
const SEGMENT_COLORS = [
  "bg-sky-500",
  "bg-violet-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-cyan-500",
  "bg-fuchsia-500",
]

/**
 * "Performance da ingestão" card (#280): a stacked bar of time per pipeline
 * step (extract → outline → chunks → fix → CR) plus tokens and tool calls.
 * Rendered in the job detail (web and, via the shared bundle, the desktop App).
 * Renders nothing when the job has no persisted per-step timing.
 */
export function IngestionPerf({ result }: { result: string | null | undefined }) {
  const perf = useMemo(() => parsePerf(result), [result])
  if (!perf) return null

  return (
    <div className="rounded-md border bg-muted/30 p-3" data-testid="ingestion-perf">
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Performance da ingestão
        </div>
        <div className="font-mono text-[12px] text-muted-foreground">
          {formatMs(perf.totalMs)} total
        </div>
      </div>

      {/* Stacked bar. */}
      <div className="mb-2 flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
        {perf.segments.map((seg, i) => (
          <div
            key={seg.name}
            className={SEGMENT_COLORS[i % SEGMENT_COLORS.length]}
            style={{ width: `${seg.pct}%` }}
            title={`${seg.label}: ${formatMs(seg.ms)} (${seg.pct.toFixed(0)}%)`}
          />
        ))}
      </div>

      {/* Per-step legend. */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
        {perf.segments.map((seg, i) => (
          <div key={seg.name} className="flex items-center gap-1.5">
            <span
              className={`size-2 shrink-0 rounded-sm ${SEGMENT_COLORS[i % SEGMENT_COLORS.length]}`}
            />
            <span className="truncate text-muted-foreground">{seg.label}</span>
            <span className="ml-auto font-mono">{formatMs(seg.ms)}</span>
          </div>
        ))}
      </div>

      {(perf.tokensIn != null || perf.toolCalls != null) && (
        <div className="mt-2 border-t pt-2 font-mono text-[11px] text-muted-foreground">
          {perf.tokensIn != null && <span>tokens {perf.tokensIn}↓</span>}
          {perf.tokensOut != null && <span> / {perf.tokensOut}↑</span>}
          {perf.toolCalls != null && <span> · {perf.toolCalls} tool calls</span>}
        </div>
      )}
    </div>
  )
}
