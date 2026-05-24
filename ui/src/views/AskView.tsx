import { useEffect, useRef, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { Sparkles, Send, Save } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { QueryResult } from "@/types"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { useCrStore } from "@/stores/crs"

const SUGGESTED = [
  "What are the trade-offs of RAG vs fine-tuning?",
  "How does attention work?",
  "What is chunking?",
]

interface HistoryItem {
  question: string
  at: number
}

export function AskView() {
  const navigate = useNavigate()
  const [question, setQuestion] = useState("")
  const [save, setSave] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const refetchCrs = useCrStore((s) => s.fetch)
  const [params] = useSearchParams()
  const askRef = useRef(false)

  async function ask(q: string) {
    const query = q.trim()
    if (!query) return
    setLoading(true)
    setResult(null)
    try {
      const startRes = await api.ask(query, save)
      if (startRes && typeof startRes === "object" && "job_id" in startRes) {
        const jobId = (startRes as any).job_id
        while (true) {
          const job = await api.getJob(jobId)
          if (job.status === "done") {
            if (job.result) {
              const res = JSON.parse(job.result) as QueryResult
              setResult(res)
              setHistory((h) => [{ question: query, at: Date.now() }, ...h].slice(0, 20))
              if (res.change_request_id) {
                await refetchCrs()
                toast.success(`Saved as ${res.change_request_id}`)
              }
            } else {
              toast.error("No result returned from job")
            }
            break
          } else if (job.status === "error") {
            toast.error(job.error || "Ask job failed")
            break
          }
          await new Promise((resolve) => setTimeout(resolve, 1000))
        }
      } else {
        const res = startRes as unknown as QueryResult
        setResult(res)
        setHistory((h) => [{ question: query, at: Date.now() }, ...h].slice(0, 20))
        if (res.change_request_id) {
          await refetchCrs()
          toast.success(`Saved as ${res.change_request_id}`)
        }
      }
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // honor ?q= from the command palette (ask once)
  useEffect(() => {
    const q = params.get("q")
    if (q && !askRef.current) {
      askRef.current = true
      setQuestion(q)
      ask(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const sourceList = result
    ? [
        ...new Set(
          result.citations
            .map((c) => c.page ?? c.source)
            .filter((x): x is string => Boolean(x)),
        ),
      ]
    : []

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[760px]">
        <h1 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold">
          <Sparkles className="size-5 text-primary" /> Ask the wiki
        </h1>

        <div className="flex gap-2">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") ask(question)
            }}
            placeholder="Ask a question grounded in your wiki…  (⌘↵ to send)"
            className="min-h-[64px] flex-1"
          />
          <Button
            onClick={() => ask(question)}
            disabled={loading || !question.trim()}
            className="h-auto gap-1.5"
          >
            <Send className="size-4" /> Ask
          </Button>
        </div>
        <label className="mt-2 flex items-center gap-2 text-[13px] text-muted-foreground">
          <Checkbox checked={save} onCheckedChange={(v) => setSave(Boolean(v))} />
          Save answer as a wiki page (creates a change request)
        </label>

        {!result && !loading && (
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTED.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setQuestion(s)
                  ask(s)
                }}
                className="rounded-full border bg-card px-3 py-1 text-[12px] text-muted-foreground hover:border-primary hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <hr className="my-5 border-border" />

        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}

        {result && (
          <div>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Answer
            </div>
            <MarkdownReader
              content={result.answer}
              onWikiLink={(t) =>
                navigate(`/wiki?q=${encodeURIComponent(t)}`)
              }
            />
            {sourceList.length > 0 && (
              <div className="mt-4 rounded-lg border bg-card p-3">
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Sources used
                </div>
                <ul className="space-y-0.5">
                  {sourceList.map((s) => (
                    <li key={s} className="font-mono text-[12px] text-muted-foreground">
                      · {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.suggested_page && !result.change_request_id && (
              <Button
                variant="outline"
                size="sm"
                className="mt-3 gap-1.5"
                onClick={() => ask(question)}
              >
                <Save className="size-4" /> Save as wiki page →
              </Button>
            )}
          </div>
        )}

        {history.length > 0 && (
          <>
            <hr className="my-5 border-border" />
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              History
            </div>
            <ul className="space-y-1">
              {history.map((h, i) => (
                <li key={i}>
                  <button
                    onClick={() => {
                      setQuestion(h.question)
                      ask(h.question)
                    }}
                    className="text-left text-[13px] text-muted-foreground hover:text-foreground"
                  >
                    · {h.question}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
