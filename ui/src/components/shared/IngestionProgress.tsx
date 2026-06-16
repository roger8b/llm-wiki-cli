import { useMemo } from "react"
import { Check, Loader2, FileText, Search, Wrench, AlertTriangle } from "lucide-react"
import type { IngestEvent } from "@/types"
import { cn } from "@/lib/utils"

/** A step on the timeline, folded from its start/end events. */
interface TimelineStep {
  name: string
  durationMs?: number
  done: boolean
}

const STEP_LABELS: Record<string, string> = {
  extracting: "Reading source",
  outlining: "Planning concepts",
  running_agent: "Agent reading & writing pages",
  fixing_structural_issues: "Fixing structural issues",
  creating_change_request: "Preparing change request",
}

function stepLabel(name: string): string {
  if (STEP_LABELS[name]) return STEP_LABELS[name]
  const chunk = /^chunk (\d+)\/(\d+)$/.exec(name)
  if (chunk) return `Chunk ${chunk[1]} of ${chunk[2]}`
  return name
}

/** Fold step start/end events into ordered timeline steps. */
export function foldSteps(events: IngestEvent[]): TimelineStep[] {
  const order: string[] = []
  const byName = new Map<string, TimelineStep>()
  for (const ev of events) {
    if (ev.kind !== "step") continue
    const name = ev.payload?.name
    if (!name) continue
    let step = byName.get(name)
    if (!step) {
      step = { name, done: false }
      byName.set(name, step)
      order.push(name)
    }
    if (ev.payload?.status === "end") {
      step.done = true
      step.durationMs = ev.payload?.duration_ms
    }
  }
  return order.map((n) => byName.get(n)!)
}

/** Estimate remaining time from finished chunk-pass durations (#274). */
export function estimateEtaMs(events: IngestEvent[]): number | null {
  const durations: number[] = []
  let total = 0
  for (const ev of events) {
    const m = ev.kind === "step" && /^chunk (\d+)\/(\d+)$/.exec(ev.payload?.name ?? "")
    if (!m) continue
    total = Number(m[2])
    if (ev.payload?.status === "end" && typeof ev.payload?.duration_ms === "number") {
      durations.push(ev.payload.duration_ms)
    }
  }
  if (durations.length === 0 || total === 0) return null
  const avg = durations.reduce((a, b) => a + b, 0) / durations.length
  const remaining = total - durations.length
  return remaining > 0 ? Math.round(avg * remaining) : null
}

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

interface Props {
  events: IngestEvent[]
  pagesStaged: number
  running: boolean
}

/**
 * Live ingestion timeline (#274): steps with durations, recent tool calls, the
 * staging/token counters, an ETA and any failure/quality signals — all derived
 * from the SSE `ingest_event` stream collected in the ingest store.
 */
export function IngestionProgress({ events, pagesStaged, running }: Props) {
  const steps = useMemo(() => foldSteps(events), [events])
  const recentTools = useMemo(
    () =>
      events
        .filter((e) => e.kind === "tool_start")
        .slice(-4)
        .reverse(),
    [events],
  )
  const warnings = useMemo(() => events.filter((e) => e.kind === "warning"), [events])
  const tokens = useMemo(() => {
    let tin = 0
    let tout = 0
    for (const e of events) {
      if (e.kind !== "telemetry") continue
      tin += e.payload?.tokens_in ?? 0
      tout += e.payload?.tokens_out ?? 0
    }
    return { tin, tout }
  }, [events])
  const etaMs = useMemo(() => (running ? estimateEtaMs(events) : null), [events, running])

  if (events.length === 0) return null

  return (
    <div className="space-y-3" data-testid="ingestion-progress">
      {/* Step timeline */}
      <ol className="space-y-1">
        {steps.map((s, i) => {
          const active = running && i === steps.length - 1 && !s.done
          return (
            <li key={s.name} className="flex items-center gap-2 text-[12px]">
              {s.done ? (
                <Check className="size-3.5 shrink-0 text-apply" />
              ) : active ? (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
              ) : (
                <Check className="size-3.5 shrink-0 text-muted-foreground/40" />
              )}
              <span className={cn("flex-1", s.done ? "text-foreground" : "text-muted-foreground")}>
                {stepLabel(s.name)}
              </span>
              {s.durationMs != null && (
                <span className="font-mono text-[11px] text-muted-foreground">
                  {fmtMs(s.durationMs)}
                </span>
              )}
            </li>
          )
        })}
      </ol>

      {/* Recent tool calls */}
      {recentTools.length > 0 && (
        <div className="space-y-0.5 border-t pt-2">
          {recentTools.map((e) => {
            const tool = e.payload?.tool ?? "tool"
            const Icon =
              tool.includes("search") || tool.includes("related")
                ? Search
                : tool.includes("write") || tool.includes("edit")
                  ? FileText
                  : Wrench
            return (
              <div
                key={e.id}
                className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground"
              >
                <Icon className="size-3 shrink-0" />
                <span className="truncate">
                  {tool}
                  {e.payload?.args ? `(${e.payload.args})` : ""}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Counters + ETA */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t pt-2 text-[11px] text-muted-foreground">
        <span>
          <span className="font-medium text-foreground">{pagesStaged}</span> pages staged
        </span>
        {tokens.tin > 0 && (
          <span>
            <span className="font-medium text-foreground">{tokens.tin + tokens.tout}</span> tokens
          </span>
        )}
        {etaMs != null && (
          <span>
            ~<span className="font-medium text-foreground">{fmtMs(etaMs)}</span> left
          </span>
        )}
      </div>

      {/* Failure / quality signals */}
      {warnings.length > 0 && (
        <div className="space-y-1 border-t pt-2">
          {warnings.map((e, i) => (
            <div
              key={e.id ?? i}
              className="flex items-start gap-1.5 text-[11px] text-amber-600 dark:text-amber-500"
            >
              <AlertTriangle className="mt-0.5 size-3 shrink-0" />
              <span>{e.payload?.message ?? "warning"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
