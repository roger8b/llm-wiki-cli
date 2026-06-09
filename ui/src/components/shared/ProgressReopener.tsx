import { Check, Loader2, AlertCircle, Ban } from "lucide-react"
import { useIngestStore } from "@/stores/ingest"

/**
 * Floating chip shown when the progress drawer was minimized (closed via X) but
 * a run is still in flight or recently finished. Click to reopen the drawer —
 * so closing the modal never loses the processing status.
 */
export function ProgressReopener() {
  const { open, status, title, reopen } = useIngestStore()

  if (open || status === "idle") return null

  const running = status === "running"

  return (
    <button
      onClick={reopen}
      className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border bg-card px-3.5 py-2 text-[12px] shadow-lg hover:border-primary"
      title="Reopen processing status"
    >
      {running ? (
        <Loader2 className="size-4 animate-spin text-primary" />
      ) : status === "error" ? (
        <AlertCircle className="size-4 text-rejected" />
      ) : status === "cancelled" ? (
        <Ban className="size-4 text-muted-foreground" />
      ) : (
        <Check className="size-4 text-apply" />
      )}
      <span className="max-w-[200px] truncate font-medium">{title || "Processing"}</span>
      <span className="text-muted-foreground">
        {running ? "running…" : "— reopen"}
      </span>
    </button>
  )
}
