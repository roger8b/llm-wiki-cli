import { useNavigate } from "react-router-dom"
import { Check, Loader2, X, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useIngestStore } from "@/stores/ingest"
import { cn } from "@/lib/utils"

export function ProgressDrawer() {
  const navigate = useNavigate()
  const { open, title, steps, status, crId, error, close } = useIngestStore()

  if (!open) return null

  const running = status === "running"

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[440px] max-w-[calc(100vw-2rem)] rounded-lg border bg-card shadow-lg">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        {running ? (
          <Loader2 className="size-4 animate-spin text-primary" />
        ) : status === "error" ? (
          <AlertCircle className="size-4 text-rejected" />
        ) : (
          <Check className="size-4 text-apply" />
        )}
        <span className="flex-1 truncate text-[13px] font-medium">{title}</span>
        <button
          onClick={close}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="max-h-[240px] space-y-1.5 overflow-y-auto px-4 py-3 font-mono text-[12px]">
        {steps.map((s, i) => {
          const last = i === steps.length - 1
          const settled = !running || !last
          return (
            <div key={i} className="flex items-center gap-2">
              {settled ? (
                <Check className="size-3.5 shrink-0 text-apply" />
              ) : (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
              )}
              <span className={cn(settled ? "text-foreground" : "text-muted-foreground")}>
                {s}
              </span>
            </div>
          )
        })}
        {status === "error" && (
          <div className="text-rejected">✗ {error}</div>
        )}
      </div>

      {!running && (
        <div className="flex items-center justify-between border-t px-4 py-3">
          {status === "done" && crId ? (
            <>
              <span className="font-mono text-[12px] text-muted-foreground">
                {crId} created
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    close()
                    navigate("/review")
                  }}
                >
                  Review now →
                </Button>
                <Button size="sm" variant="outline" onClick={close}>
                  Close
                </Button>
              </div>
            </>
          ) : (
            <>
              {status === "done" && (
                <span className="text-[12px] text-muted-foreground">
                  Done — no changes proposed.
                </span>
              )}
              <Button size="sm" variant="outline" className="ml-auto" onClick={close}>
                Close
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
