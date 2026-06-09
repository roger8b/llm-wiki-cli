import { useEffect, useState } from "react"
import { ListTodo, Loader2, AlertCircle, RefreshCw, Ban } from "lucide-react"
import { useJobStore } from "@/stores/jobs"
import type { Job } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"

const PROGRESS_LABELS: Record<string, string> = {
  running_agent: "Agent working…",
  creating_change_request: "Preparing change request…",
}

function describe(type: string, payloadStr?: string | null) {
  if (!payloadStr) return type
  try {
    const p = JSON.parse(payloadStr)
    if (type === "ingest") return `Ingest: ${p.source?.split("/").pop() || p.source}`
    if (type === "ask") return `Ask: "${p.question}"`
    if (type === "maintain") return `Maintain (${p.semantic ? "semantic" : "structural"})`
    if (type === "lint") return `Lint (${p.semantic ? "semantic" : "structural"})`
  } catch {
    // ignore
  }
  return type
}

function safeParse(s?: string | null): Record<string, unknown> | null {
  if (!s) return null
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}

function StatusBadge({ status }: { status: Job["status"] }) {
  if (status === "queued")
    return <Badge variant="outline" className="bg-secondary/30 text-muted-foreground border-muted-foreground/20">Queued</Badge>
  if (status === "running")
    return <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20 animate-pulse">Running</Badge>
  if (status === "done")
    return <Badge variant="default" className="bg-apply/15 text-apply border-apply/20 hover:bg-apply/25">Completed</Badge>
  if (status === "error")
    return <Badge variant="destructive" className="bg-rejected/15 text-rejected border-rejected/20 hover:bg-rejected/25">Failed</Badge>
  return <Badge variant="outline" className="bg-secondary/30 text-muted-foreground border-muted-foreground/20">Cancelled</Badge>
}

function formatDuration(start: string, end?: string | null) {
  if (!end) return "Running…"
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (isNaN(ms) || ms < 0) return "—"
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

/** Compact one-line outcome for the table / modal. */
function resultSummary(job: Job) {
  if (job.error) return <span className="text-rejected">{job.error}</span>
  if (job.status === "running")
    return (
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        {job.progress ? (PROGRESS_LABELS[job.progress] ?? job.progress) : "Working…"}
      </span>
    )
  const r = safeParse(job.result)
  if (!r) return <span className="text-muted-foreground">—</span>
  if (r.skipped) return <span className="text-muted-foreground">Skipped — already processed</span>
  if (r.cancelled) return <span className="text-muted-foreground">Cancelled</span>
  if (job.type === "ingest") {
    const cr = r.cr as string | null
    return cr ? (
      <span>CR <strong className="font-mono">{cr}</strong> · {String(r.files ?? 0)} files</span>
    ) : (
      <span className="text-muted-foreground">No changes proposed</span>
    )
  }
  if (job.type === "ask")
    return <span>Answered{r.change_request_id ? ` · CR ${r.change_request_id}` : ""}</span>
  if (job.type === "maintain")
    return r.change_request_id ? (
      <span>Fixes <strong className="font-mono">{String(r.change_request_id)}</strong></span>
    ) : (
      <span className="text-muted-foreground">No fixes needed</span>
    )
  if (job.type === "lint")
    return <span>{Array.isArray(r.findings) ? r.findings.length : 0} issues</span>
  return <span className="text-muted-foreground">Completed</span>
}

/** Plain-text outcome (for the semaphore tooltip). */
function outcomeText(job: Job): string {
  if (job.error) return job.error
  if (job.status === "running")
    return job.progress ? (PROGRESS_LABELS[job.progress] ?? job.progress) : "Working…"
  if (job.status === "queued") return "Queued"
  const r = safeParse(job.result)
  if (r?.skipped) return "Skipped — already processed"
  if (job.status === "cancelled" || r?.cancelled) return "Cancelled"
  if (job.type === "ingest") {
    const cr = r?.cr as string | null
    return cr ? `CR ${cr} · ${String(r?.files ?? 0)} files` : "No changes proposed"
  }
  if (job.type === "ask") return `Answered${r?.change_request_id ? ` · CR ${r.change_request_id}` : ""}`
  if (job.type === "maintain")
    return r?.change_request_id ? `Fixes ${String(r.change_request_id)}` : "No fixes needed"
  if (job.type === "lint") return `${Array.isArray(r?.findings) ? r.findings.length : 0} issues`
  return "Completed"
}

/**
 * Outcome traffic-light. Encodes the *result* (not just status): green = produced
 * output, amber = skipped/no-op, red = failed, gray = cancelled/queued, blue = running.
 */
function Semaphore({ job }: { job: Job }) {
  // Default (cancelled / unknown) is neutral gray.
  let color = "bg-muted-foreground/40"
  let pulse = false
  if (job.status === "running" || job.status === "queued") {
    color = "bg-primary"
    pulse = job.status === "running"
  } else if (job.status === "error") {
    color = "bg-rejected"
  } else if (job.status === "done") {
    // distinguish "produced something" from "no-op / skipped"
    const r = safeParse(job.result)
    const noop =
      r?.skipped ||
      (job.type === "ingest" && !r?.cr) ||
      (job.type === "maintain" && !r?.change_request_id)
    color = noop ? "bg-amber-500" : "bg-apply"
  }
  return (
    <span
      title={outcomeText(job)}
      className={`inline-block size-2.5 rounded-full ${color} ${pulse ? "animate-pulse" : ""}`}
    />
  )
}

export function JobsView() {
  const { jobs, loading, error, cancellingIds, fetch, cancel } = useJobStore()
  const [selected, setSelected] = useState<Job | null>(null)

  useEffect(() => {
    fetch()
  }, [fetch])

  const hasActive = jobs.some((j) => j.status === "running" || j.status === "queued")
  useEffect(() => {
    if (!hasActive) return
    const t = setInterval(() => fetch(), 1500)
    return () => clearInterval(t)
  }, [hasActive, fetch])

  // Keep the open details dialog in sync with live updates.
  const selectedLive = selected ? jobs.find((j) => j.id === selected.id) ?? selected : null

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[720px]">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold">
            <ListTodo className="size-5 text-primary" /> Background jobs
          </h1>
          <Button variant="outline" size="sm" onClick={() => fetch()} disabled={loading} className="gap-1.5">
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-apply" /> Produced output</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-amber-500" /> Skipped / no-op</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-rejected" /> Failed</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-primary" /> Running</span>
          <span className="ml-auto">Click a row for details</span>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-[13px] text-destructive">
            <AlertCircle className="size-4 shrink-0" />
            <span>Error fetching jobs: {error}</span>
          </div>
        )}

        {jobs.length === 0 ? (
          <div className="rounded-lg border border-dashed py-12 text-center">
            {loading ? (
              <div className="flex flex-col items-center justify-center gap-2">
                <Loader2 className="size-6 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Loading jobs…</span>
              </div>
            ) : (
              <>
                <p className="text-[13px] text-muted-foreground">No background jobs recorded.</p>
                <p className="mx-auto mt-1 max-w-[420px] text-[12px] text-muted-foreground">
                  Ingestion, queries and maintenance tasks show up here as they run.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border bg-card">
            <Table className="w-full table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead className="w-[112px]">Status</TableHead>
                  <TableHead className="w-[80px]">Duration</TableHead>
                  <TableHead className="w-[64px] text-center">Result</TableHead>
                  <TableHead className="w-[84px] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => {
                  const active = job.status === "running" || job.status === "queued"
                  return (
                    <TableRow
                      key={job.id}
                      onClick={() => setSelected(job)}
                      className="cursor-pointer"
                    >
                      <TableCell className="truncate text-xs font-medium" title={describe(job.type, job.payload)}>
                        {describe(job.type, job.payload)}
                      </TableCell>
                      <TableCell><StatusBadge status={job.status} /></TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDuration(job.created_at, job.completed_at)}
                      </TableCell>
                      <TableCell className="text-center"><Semaphore job={job} /></TableCell>
                      <TableCell className="text-right">
                        {active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={cancellingIds.includes(job.id)}
                            onClick={(e) => {
                              e.stopPropagation()
                              cancel(job.id)
                            }}
                            className="h-7 gap-1 px-2 text-[12px] text-muted-foreground"
                          >
                            <Ban className="size-3.5" />
                            {cancellingIds.includes(job.id) ? "…" : "Cancel"}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <JobDetailsDialog
        job={selectedLive}
        onClose={() => setSelected(null)}
        cancelling={selectedLive ? cancellingIds.includes(selectedLive.id) : false}
        onCancel={(id) => cancel(id)}
      />
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-1 text-[13px]">
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words">{value}</span>
    </div>
  )
}

function JobDetailsDialog({
  job,
  onClose,
  cancelling,
  onCancel,
}: {
  job: Job | null
  onClose: () => void
  cancelling: boolean
  onCancel: (id: number) => void
}) {
  const r = job ? safeParse(job.result) : null
  const exec = (r?.execution ?? null) as Record<string, unknown> | null
  const active = job?.status === "running" || job?.status === "queued"

  return (
    <Dialog open={!!job} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-[560px]">
        {job && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-[15px]">
                <span className="font-mono text-muted-foreground">#{job.id}</span>
                {describe(job.type, job.payload)}
              </DialogTitle>
              <DialogDescription>Background job details</DialogDescription>
            </DialogHeader>

            <div className="space-y-0.5">
              <Row label="Status" value={<StatusBadge status={job.status} />} />
              <Row label="Type" value={<span className="font-mono">{job.type}</span>} />
              {job.status === "running" && job.progress && (
                <Row label="Progress" value={PROGRESS_LABELS[job.progress] ?? job.progress} />
              )}
              <Row label="Started" value={formatTime(job.created_at)} />
              {job.completed_at && <Row label="Finished" value={formatTime(job.completed_at)} />}
              <Row label="Duration" value={formatDuration(job.created_at, job.completed_at)} />
              <Row label="Outcome" value={resultSummary(job)} />
              {job.error && <Row label="Error" value={<span className="text-rejected">{job.error}</span>} />}
            </div>

            {exec && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Execution
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[12px]">
                  <span className="text-muted-foreground">model</span><span className="truncate">{String(exec.model ?? "—")}</span>
                  <span className="text-muted-foreground">tokens in</span><span>{String(exec.tokens_in ?? "—")}</span>
                  <span className="text-muted-foreground">tokens out</span><span>{String(exec.tokens_out ?? "—")}</span>
                  <span className="text-muted-foreground">tool calls</span><span>{String(exec.tool_calls ?? "—")}</span>
                  <span className="text-muted-foreground">latency</span><span>{exec.latency_ms != null ? `${exec.latency_ms}ms` : "—"}</span>
                  <span className="text-muted-foreground">fallback</span><span>{String(exec.used_fallback ?? false)}</span>
                </div>
              </div>
            )}

            <DialogFooter>
              {active && (
                <Button
                  variant="outline"
                  disabled={cancelling}
                  onClick={() => onCancel(job.id)}
                  className="gap-1.5"
                >
                  <Ban className="size-4" /> {cancelling ? "Cancelling…" : "Cancel job"}
                </Button>
              )}
              <Button variant="ghost" onClick={onClose}>Close</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
