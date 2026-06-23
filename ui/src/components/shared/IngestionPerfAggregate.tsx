import { useEffect, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { api } from "@/lib/api"
import { formatMs, stepLabel } from "@/lib/perf"
import type { StepStats } from "@/types"

/**
 * Aggregate "Performance da ingestão" card (#280): average time per pipeline
 * step over the last N ingestions, with a regression badge when the latest run
 * runs materially slower than the prior baseline (#276). Renders nothing until
 * there is at least one timed ingestion to summarize.
 */
export function IngestionPerfAggregate() {
  const [stats, setStats] = useState<StepStats | null>(null)

  useEffect(() => {
    let live = true
    api
      .jobsStepStats()
      .then((s) => live && setStats(s))
      .catch(() => live && setStats(null))
    return () => {
      live = false
    }
  }, [])

  if (!stats || stats.runs === 0) return null

  const maxAvg = Math.max(1, ...stats.steps.map((s) => s.avg_ms))
  const reg = stats.regression

  return (
    <div className="rounded-md border bg-muted/20 p-3" data-testid="ingestion-perf-aggregate">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Tempo médio por etapa · últimas {stats.runs} ingestões
        </div>
        {reg.is_regression && (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-600">
            <AlertTriangle className="size-3" />
            regressão: {formatMs(reg.latest_total_ms)} vs {formatMs(reg.baseline_avg_ms)}
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        {stats.steps.map((s) => (
          <div key={s.name} className="flex items-center gap-2 text-[12px]">
            <span className="w-40 shrink-0 truncate text-muted-foreground">{stepLabel(s.name)}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-sky-500"
                style={{ width: `${(s.avg_ms / maxAvg) * 100}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right font-mono">{formatMs(s.avg_ms)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
