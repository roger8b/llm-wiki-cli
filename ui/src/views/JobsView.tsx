import { useEffect } from "react"
import { ListTodo, Loader2, AlertCircle, RefreshCw } from "lucide-react"
import { useJobStore } from "@/stores/jobs"
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

export function JobsView() {
  const { jobs, loading, error, fetch } = useJobStore()

  useEffect(() => {
    fetch()
  }, [fetch])

  function formatDuration(start: string, end?: string | null) {
    if (!end) return "Running..."
    const s = new Date(start).getTime()
    const e = new Date(end).getTime()
    const diffMs = e - s
    if (isNaN(diffMs) || diffMs < 0) return "-"
    if (diffMs < 1000) return `${diffMs}ms`
    return `${(diffMs / 1000).toFixed(1)}s`
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  function getJobDescription(type: string, payloadStr?: string | null) {
    if (!payloadStr) return type
    try {
      const payload = JSON.parse(payloadStr)
      if (type === "ingest") {
        return `Ingest: ${payload.source?.split("/").pop() || payload.source}`
      }
      if (type === "ask") {
        return `Ask: "${payload.question}"`
      }
      if (type === "maintain") {
        return `Maintain (${payload.semantic ? "semantic" : "structural"})`
      }
      if (type === "lint") {
        return `Lint (${payload.semantic ? "semantic" : "structural"})`
      }
    } catch {
      // ignore
    }
    return type
  }

  function getJobResultSummary(type: string, resultStr?: string | null, errorStr?: string | null) {
    if (errorStr) {
      return <span className="text-rejected text-xs font-medium">{errorStr}</span>
    }
    if (!resultStr) return <span className="text-muted-foreground text-xs">—</span>
    try {
      const result = JSON.parse(resultStr)
      if (type === "ingest") {
        return (
          <span className="text-xs">
            CR created: <strong className="font-mono">{result.cr}</strong> ({result.files} files)
          </span>
        )
      }
      if (type === "ask") {
        return (
          <span className="text-xs">
            Answered{result.change_request_id ? ` (CR: ${result.change_request_id})` : ""}
          </span>
        )
      }
      if (type === "maintain") {
        return (
          <span className="text-xs">
            {result.change_request_id ? (
              <>Proposed fixes: <strong className="font-mono">{result.change_request_id}</strong></>
            ) : (
              "No fixes needed"
            )}
          </span>
        )
      }
      if (type === "lint") {
        return (
          <span className="text-xs">
            Found {result.findings?.length || 0} issues
          </span>
        )
      }
    } catch {
      // ignore
    }
    return <span className="text-muted-foreground text-xs">Completed</span>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[860px]">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold">
            <ListTodo className="size-5 text-primary" /> Background jobs
          </h1>
          <Button variant="outline" size="sm" onClick={() => fetch()} disabled={loading} className="gap-1.5">
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
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
                <span className="text-xs text-muted-foreground">Loading jobs...</span>
              </div>
            ) : (
              <>
                <p className="text-[13px] text-muted-foreground">
                  No background jobs recorded.
                </p>
                <p className="mx-auto mt-1 max-w-[420px] text-[12px] text-muted-foreground">
                  Jobs like file ingestion, query execution, or maintenance tasks will show up here as they run.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[60px]">ID</TableHead>
                  <TableHead className="w-[180px]">Job</TableHead>
                  <TableHead className="w-[100px]">Status</TableHead>
                  <TableHead className="w-[100px]">Time</TableHead>
                  <TableHead className="w-[100px]">Duration</TableHead>
                  <TableHead>Result / Error</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      #{job.id}
                    </TableCell>
                    <TableCell className="font-medium text-xs">
                      {getJobDescription(job.type, job.payload)}
                    </TableCell>
                    <TableCell>
                      {job.status === "queued" && (
                        <Badge variant="outline" className="bg-secondary/30 text-muted-foreground border-muted-foreground/20">
                          Queued
                        </Badge>
                      )}
                      {job.status === "running" && (
                        <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20 animate-pulse">
                          Running
                        </Badge>
                      )}
                      {job.status === "done" && (
                        <Badge variant="default" className="bg-apply/15 text-apply border-apply/20 hover:bg-apply/25">
                          Completed
                        </Badge>
                      )}
                      {job.status === "error" && (
                        <Badge variant="destructive" className="bg-rejected/15 text-rejected border-rejected/20 hover:bg-rejected/25">
                          Failed
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(job.created_at)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDuration(job.created_at, job.completed_at)}
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate text-xs">
                      {getJobResultSummary(job.type, job.result, job.error)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  )
}
