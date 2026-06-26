import { AlertTriangle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

/**
 * Global drift banner (#306): shown above the main content when the index is
 * stale, with a one-click "Reindex" affordance. Renders nothing on a healthy
 * index so it costs nothing in the common case.
 */
export function DriftBanner({
  stale,
  drift,
  busy,
  onReindex,
}: {
  stale: boolean
  /** db_pages − disk_files (negative = rows missing files; positive = files missing rows). */
  drift: number
  busy?: boolean
  onReindex: () => void
}) {
  if (!stale) return null

  const pending =
    drift > 0
      ? `${drift} ${Math.abs(drift) === 1 ? "file" : "files"} not indexed`
      : `${Math.abs(drift)} orphaned ${Math.abs(drift) === 1 ? "row" : "rows"}`

  return (
    <div
      role="status"
      data-testid="drift-banner"
      className="flex items-center gap-3 border-b border-pending/30 bg-pending/10 px-6 py-2.5 text-[12.5px] text-pending"
    >
      <AlertTriangle className="size-4 shrink-0" />
      <span className="flex-1">
        <strong>Index is out of date</strong> — {pending}.
      </span>
      <Button
        size="sm"
        variant="outline"
        onClick={onReindex}
        disabled={busy}
        className="h-7 gap-1.5 border-pending/30 bg-background text-pending hover:bg-pending/15"
      >
        <RefreshCw className={busy ? "size-3.5 animate-spin" : "size-3.5"} />
        {busy ? "Reindexing…" : "Reindex"}
      </Button>
    </div>
  )
}