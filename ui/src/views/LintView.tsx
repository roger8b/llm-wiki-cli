import { useState } from "react"
import { ShieldCheck, AlertTriangle, Info, XCircle, Loader2, Wrench } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { LintFinding, LintSeverity } from "@/types"
import { Button } from "@/components/ui/button"
import { useIngestStore } from "@/stores/ingest"
import { useCrStore } from "@/stores/crs"

const SEVERITY_META: Record<
  LintSeverity,
  { label: string; icon: typeof Info; cls: string }
> = {
  error: { label: "Errors", icon: XCircle, cls: "text-rejected" },
  warn: { label: "Warnings", icon: AlertTriangle, cls: "text-pending" },
  info: { label: "Info", icon: Info, cls: "text-primary" },
}

function FindingCard({ f }: { f: LintFinding }) {
  const meta = SEVERITY_META[f.severity] ?? SEVERITY_META.info
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="flex items-start gap-2">
        <meta.icon className={cn("mt-0.5 size-4 shrink-0", meta.cls)} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px]">{f.message}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="rounded border bg-secondary px-1.5 py-px font-mono">
              {f.kind}
            </span>
            {f.pages.map((p) => (
              <span key={p} className="font-mono">
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export function LintView() {
  const [findings, setFindings] = useState<LintFinding[] | null>(null)
  const [loading, setLoading] = useState<"structural" | "semantic" | null>(null)
  const runIngest = useIngestStore((s) => s.run)
  const refetchCrs = useCrStore((s) => s.fetch)

  async function run(semantic: boolean) {
    setLoading(semantic ? "semantic" : "structural")
    try {
      const res = await api.lint(semantic)
      setFindings(res.findings)
      toast.success(`Lint done — ${res.findings.length} finding(s)`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(null)
    }
  }

  async function proposeFixes() {
    await runIngest("Proposing fixes for lint issues…", () => api.maintain(false))
    await refetchCrs()
  }

  const groups: LintSeverity[] = ["error", "warn", "info"]
  const hasFixable = findings?.some((f) => f.severity === "error") ?? false

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[760px]">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold">
            <ShieldCheck className="size-5 text-primary" /> Lint report
          </h1>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => run(false)}
              disabled={loading !== null}
            >
              {loading === "structural" && (
                <Loader2 className="size-4 animate-spin" />
              )}
              Run structural
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => run(true)}
              disabled={loading !== null}
            >
              {loading === "semantic" && (
                <Loader2 className="size-4 animate-spin" />
              )}
              Run + LLM
            </Button>
            {findings && findings.length > 0 && (
              <Button
                size="sm"
                onClick={proposeFixes}
                disabled={loading !== null}
                className="gap-1.5"
                title={
                  hasFixable
                    ? "Ask the LLM to fix the issues (creates a change request)"
                    : "Propose fixes for these issues via the LLM"
                }
              >
                <Wrench className="size-4" /> Propose fixes
              </Button>
            )}
          </div>
        </div>

        {findings === null ? (
          <div className="rounded-lg border border-dashed py-12 text-center text-[13px] text-muted-foreground">
            Run a lint check to audit the knowledge base.
          </div>
        ) : findings.length === 0 ? (
          <div className="rounded-lg border border-apply/30 bg-apply/5 py-12 text-center text-[13px] text-apply">
            ✓ No issues found. The wiki is healthy.
          </div>
        ) : (
          <div className="space-y-5">
            {groups.map((sev) => {
              const items = findings.filter((f) => f.severity === sev)
              if (items.length === 0) return null
              const meta = SEVERITY_META[sev]
              return (
                <div key={sev}>
                  <div
                    className={cn(
                      "mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide",
                      meta.cls,
                    )}
                  >
                    <meta.icon className="size-3.5" />
                    {meta.label} ({items.length})
                  </div>
                  <div className="space-y-2">
                    {items.map((f, i) => (
                      <FindingCard key={i} f={f} />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
