import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Activity, AlertCircle, BarChart3, Loader2, RefreshCw } from "lucide-react"
import { api } from "@/lib/api"
import { useCrStore } from "@/stores/crs"
import { useIndexHealthStore } from "@/stores/indexHealth"
import { IndexHealthCard } from "@/components/shared/IndexHealthCard"
import type { Job, ModelStats } from "@/types"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table"

const PERIODS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
]

export function sinceDate(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export function fmtNum(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n)}`
}

export function fmtCost(c: number | null): string {
  if (c === null) return "—"
  return c === 0 ? "$0" : `$${c.toFixed(c < 0.01 ? 4 : 2)}`
}

export function fmtPct(r: number): string {
  return `${Math.round(r * 100)}%`
}

export interface StatsTotals {
  runs: number
  tokens: number
  cost: number
  hasCost: boolean
  fallback: number
  rejRate: number
}

/** Aggregate per-model stats into the summary-card totals. Pure for testing. */
export function summarize(stats: ModelStats[]): StatsTotals {
  const runs = stats.reduce((a, s) => a + s.runs, 0)
  const tokens = stats.reduce(
    (a, s) => a + (s.tokens_in_avg + s.tokens_out_avg) * s.runs,
    0,
  )
  const cost = stats.reduce((a, s) => a + (s.est_cost_usd ?? 0), 0)
  const hasCost = stats.some((s) => s.est_cost_usd !== null)
  const fallback =
    runs > 0 ? stats.reduce((a, s) => a + s.fallback_rate * s.runs, 0) / runs : 0
  const applied = stats.reduce((a, s) => a + s.applied, 0)
  const rejected = stats.reduce((a, s) => a + s.rejected, 0)
  const rejRate = applied + rejected > 0 ? rejected / (applied + rejected) : 0
  return { runs, tokens, cost, hasCost, fallback, rejRate }
}

function crIdOf(job: Job): string | null {
  if (!job.result) return null
  try {
    const r = JSON.parse(job.result)
    return (r.cr as string) || (r.change_request_id as string) || null
  } catch {
    return null
  }
}

function duration(job: Job): string {
  if (!job.completed_at) return "—"
  const ms = new Date(job.completed_at).getTime() - new Date(job.created_at).getTime()
  if (isNaN(ms) || ms < 0) return "—"
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function modelOf(job: Job): string {
  if (!job.result) return "—"
  try {
    const r = JSON.parse(job.result)
    return (r.execution?.model as string) || "—"
  } catch {
    return "—"
  }
}

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 font-display text-2xl font-semibold">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

export function InsightsView() {
  const navigate = useNavigate()
  const selectCr = useCrStore((s) => s.select)
  const [days, setDays] = useState(30)
  const [stats, setStats] = useState<ModelStats[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, j] = await Promise.all([api.jobsStats(sinceDate(days)), api.listJobs()])
      setStats(s.stats)
      setJobs(j)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    load()
  }, [load])

  // Index health (#306): refresh alongside the other insights data so the
  // card never lags more than one Refresh click behind.
  const indexStatus = useIndexHealthStore((s) => s.status)
  const indexBusy = useIndexHealthStore((s) => s.busy)
  const refreshIndex = useIndexHealthStore((s) => s.refresh)
  const reindex = useIndexHealthStore((s) => s.reindex)
  useEffect(() => {
    refreshIndex()
  }, [refreshIndex])

  const totals = useMemo(() => summarize(stats), [stats])

  const recent = jobs.slice(0, 20)

  function openCr(id: string) {
    selectCr(id)
    navigate("/review")
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[920px]">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold">
            <BarChart3 className="size-5 text-primary" /> Insights
          </h1>
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border bg-card p-0.5">
              {PERIODS.map((p) => (
                <button
                  key={p.days}
                  onClick={() => setDays(p.days)}
                  className={`rounded px-2.5 py-1 text-[12px] font-medium ${
                    days === p.days
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => load()}
              disabled={loading}
              className="gap-1.5"
            >
              <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-[13px] text-destructive">
            <AlertCircle className="size-4 shrink-0" />
            <span>Could not load stats: {error}</span>
          </div>
        )}

        {/* Index health (#306): the drift/reindex control lives at the top of
            Insights so it sits next to the recent-activity feed that surfaces
            index jobs. */}
        <div className="mb-6">
          <IndexHealthCard
            status={indexStatus}
            busy={indexBusy}
            onReindex={() => reindex()}
          />
        </div>

        {loading && stats.length === 0 ? (
          <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
            <span className="text-[13px]">Loading insights…</span>
          </div>
        ) : !loading && stats.length === 0 ? (
          <div className="rounded-lg border border-dashed py-16 text-center">
            <p className="text-[13px] text-muted-foreground">No agent runs yet.</p>
            <p className="mx-auto mt-1 max-w-[420px] text-[12px] text-muted-foreground">
              Run an ingestion to populate cost, quality and latency metrics here.
            </p>
          </div>
        ) : (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Card label="Runs" value={fmtNum(totals.runs)} hint={`last ${days} days`} />
              <Card label="Tokens" value={fmtNum(totals.tokens)} hint="in + out" />
              <Card
                label="Est. cost"
                value={totals.hasCost ? fmtCost(totals.cost) : "—"}
                hint={totals.hasCost ? "known models" : "no priced models"}
              />
              <Card label="Fallback" value={fmtPct(totals.fallback)} hint={`reject ${fmtPct(totals.rejRate)}`} />
            </div>

            <div className="mb-6 overflow-hidden rounded-lg border bg-card px-4">
              <div className="px-0 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                By model
              </div>
              <Table className="w-full">
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Runs</TableHead>
                    <TableHead className="text-right">Tok in</TableHead>
                    <TableHead className="text-right">Tok out</TableHead>
                    <TableHead className="text-right">Lat p95</TableHead>
                    <TableHead className="text-right">Fallback</TableHead>
                    <TableHead className="text-right">Phantom</TableHead>
                    <TableHead className="text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stats.map((s) => (
                    <TableRow key={s.model}>
                      <TableCell className="font-mono text-xs">{s.model}</TableCell>
                      <TableCell className="text-right">{s.runs}</TableCell>
                      <TableCell className="text-right">{fmtNum(s.tokens_in_avg)}</TableCell>
                      <TableCell className="text-right">{fmtNum(s.tokens_out_avg)}</TableCell>
                      <TableCell className="text-right">{Math.round(s.latency_ms_p95)}ms</TableCell>
                      <TableCell className="text-right">{fmtPct(s.fallback_rate)}</TableCell>
                      <TableCell className="text-right">{fmtPct(s.phantom_rate)}</TableCell>
                      <TableCell className="text-right">{fmtCost(s.est_cost_usd)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}

        {recent.length > 0 && (
          <div className="overflow-hidden rounded-lg border bg-card px-4">
            <div className="flex items-center gap-1.5 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <Activity className="size-3.5" /> Recent activity
            </div>
            <Table className="w-full">
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="text-right">CR</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((job) => {
                  const cr = crIdOf(job)
                  return (
                    <TableRow key={job.id}>
                      <TableCell className="text-xs font-medium">{job.type}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {modelOf(job)}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{job.status}</TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {duration(job)}
                      </TableCell>
                      <TableCell className="text-right">
                        {cr ? (
                          <button
                            onClick={() => openCr(cr)}
                            className="font-mono text-xs text-primary hover:underline"
                          >
                            {cr}
                          </button>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
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
    </div>
  )
}
