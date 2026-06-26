import { Database, RefreshCw, AlertTriangle, CheckCircle2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { IndexStatus } from "@/types"

/**
 * Index health card (#306): shows db×disk drift, embedding health and the last
 * reindex timestamp, and lets the user trigger a reindex from the UI.
 *
 * Presentational — parent owns `status` (fetched via `api.indexStatus()`) and
 * the reindex action (calls `api.reindex()`, follows the SSE stream, refreshes
 * status). This keeps the card trivial to test (no fetch mocks in the unit
 * suite) and lets each view decide its own UX for running the job.
 */
export function IndexHealthCard({
  status,
  busy = false,
  onReindex,
  compact = false,
}: {
  status: IndexStatus | null
  busy?: boolean
  onReindex: () => void
  /** Smaller card variant for settings sidebars / tight layouts. */
  compact?: boolean
}) {
  if (!status) {
    return (
      <div
        className="rounded-lg border bg-card p-4"
        data-testid="index-health-loading"
      >
        <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Database className="size-4" />
          <span className="font-medium">Index health</span>
          <span className="ml-auto text-[12px]">Loading…</span>
        </div>
      </div>
    )
  }

  const { db_pages, disk_files, drift, stale, embeddings, last_reindex_at } = status

  return (
    <div
      className={cn(
        "rounded-lg border bg-card",
        stale ? "border-pending/40" : "border-border",
        compact ? "p-3" : "p-4",
      )}
      data-testid="index-health-card"
      data-stale={stale ? "true" : "false"}
    >
      <div className="flex items-center gap-2">
        <Database className={cn("size-4", stale ? "text-pending" : "text-primary")} />
        <span className={cn("font-medium", compact ? "text-[13px]" : "text-[13.5px]")}>
          Index health
        </span>
        {stale ? (
          <Badge
            variant="outline"
            className="ml-auto gap-1 border-pending/30 bg-pending/10 text-pending"
          >
            <AlertTriangle className="size-3" />
            Stale
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="ml-auto gap-1 border-apply/30 bg-apply/10 text-apply"
          >
            <CheckCircle2 className="size-3" />
            Up to date
          </Badge>
        )}
      </div>

      <dl
        className={cn(
          "mt-3 grid gap-x-4 gap-y-1.5 font-mono text-[12px]",
          compact ? "grid-cols-1" : "grid-cols-2",
        )}
      >
        <Row label="Pages" value={`${db_pages} / ${disk_files}`} testId="index-pages" />
        <Row
          label="Drift"
          value={formatIndexDrift(drift)}
          tone={drift === 0 ? "ok" : "warn"}
          testId="index-drift"
        />
        <Row
          label="Embeddings"
          value={
            embeddings.enabled
              ? `${embeddings.count} / ${embeddings.expected}`
              : "Disabled"
          }
          tone={!embeddings.enabled ? "muted" : embeddings.count < embeddings.expected ? "warn" : "ok"}
          testId="index-embeddings"
        />
        <Row
          label="Last reindex"
          value={formatLastReindex(last_reindex_at)}
          testId="index-last-reindex"
        />
      </dl>

      <div className="mt-3 flex items-center justify-end">
        <Button
          size="sm"
          variant={stale ? "default" : "outline"}
          onClick={onReindex}
          disabled={busy}
          className="gap-1.5"
          data-testid="reindex-button"
        >
          <RefreshCw className={cn("size-3.5", busy && "animate-spin")} />
          {busy ? "Reindexing…" : "Reindex"}
        </Button>
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  tone = "ok",
  testId,
}: {
  label: string
  value: string
  tone?: "ok" | "warn" | "muted"
  testId?: string
}) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        data-testid={testId}
        className={cn(
          "text-right",
          tone === "warn" && "text-pending",
          tone === "muted" && "text-muted-foreground",
        )}
      >
        {value}
      </dd>
    </>
  )
}

/** Format a drift number as "+N" / "0" / "-N" for the badge copy. Pure. */
export function formatIndexDrift(drift: number): string {
  if (drift === 0) return "0"
  return drift > 0 ? `+${drift}` : `${drift}`
}

/**
 * Human-readable "N min/h/d ago" for `last_reindex_at`, or "never" when null.
 * Exported + clock injection keeps this testable without sleeping.
 */
export function formatLastReindex(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "never"
  const t = new Date(iso).getTime()
  if (isNaN(t)) return "never"
  const ms = now.getTime() - t
  if (ms < 60_000) return "just now"
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}