import { useEffect, useRef, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { Sparkles, Send, ArrowUpRight, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { AskHistoryItem, QueryResult } from "@/types"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { useCrStore } from "@/stores/crs"
import { useAskStore } from "@/stores/ask"

const SUGGESTED = [
  "What are the trade-offs of RAG vs fine-tuning?",
  "How does attention work?",
  "What is chunking?",
]

export function AskView() {
  const navigate = useNavigate()
  // Question / answer / active history id live in a store so they survive
  // navigating away from this tab and back.
  const question = useAskStore((s) => s.question)
  const setQuestion = useAskStore((s) => s.setQuestion)
  const result = useAskStore((s) => s.result)
  const setResult = useAskStore((s) => s.setResult)
  const activeId = useAskStore((s) => s.activeId)
  const setActiveId = useAskStore((s) => s.setActiveId)
  // loading lives in the store so the in-flight query's loading UI survives
  // navigating away and back (the async ask() keeps running and updates it).
  const loading = useAskStore((s) => s.loading)
  const setLoading = useAskStore((s) => s.setLoading)
  const [save, setSave] = useState(false)
  const [promoting, setPromoting] = useState(false)
  const [history, setHistory] = useState<AskHistoryItem[]>([])
  const [jobId, setJobId] = useState<number | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const refetchCrs = useCrStore((s) => s.fetch)
  const [params] = useSearchParams()
  const askRef = useRef(false)

  async function loadHistory() {
    try {
      setHistory(await api.askHistory())
    } catch {
      // history is best-effort; ignore load failures
    }
  }

  useEffect(() => {
    loadHistory()
  }, [])

  async function ask(q: string) {
    const query = q.trim()
    if (!query) return
    setLoading(true)
    setResult(null)
    setActiveId(null)
    setProgress(null)
    try {
      const startRes = await api.ask(query, save)
      const startedJobId = (startRes as { job_id?: number }).job_id
      if (typeof startedJobId !== "number") {
        toast.error("Backend did not queue the question")
        return
      }
      setJobId(startedJobId)
      // Stream the job over SSE — the answer lands the instant the worker
      // finishes (no 1s polling granularity).
      await api.streamJob(startedJobId, {
        onProgress: (step) => setProgress(step),
        onResult: async (result) => {
          if (!result) {
            toast.error("No result returned from job")
            return
          }
          const res = JSON.parse(result) as QueryResult
          setResult(res)
          setActiveId(res.history_id ?? null)
          if (res.change_request_id) {
            await refetchCrs()
            toast.success(`Saved as ${res.change_request_id}`)
          }
          await loadHistory()
        },
        onCancelled: () => toast.info("Question cancelled"),
        onError: (msg) => toast.error(msg || "Ask job failed"),
      })
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
      setJobId(null)
      setProgress(null)
    }
  }

  async function cancelAsk() {
    if (jobId == null) return
    try {
      await api.cancelJob(jobId)
      toast.info("Cancelling…")
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const PROGRESS_LABELS: Record<string, string> = {
    running_agent: "Agent reading the wiki…",
    creating_change_request: "Preparing the change request…",
  }

  /** Show a previously-asked answer from history without re-running the LLM. */
  function openHistory(item: AskHistoryItem) {
    setQuestion(item.question)
    setResult({
      answer: item.answer,
      citations: item.citations,
      change_request_id: item.change_request_id,
    })
    setActiveId(item.id)
  }

  async function promote() {
    if (!result || !question.trim()) return
    setPromoting(true)
    try {
      const { change_request_id } = await api.promoteAnswer({
        question: question.trim(),
        answer: result.answer,
        history_id: activeId ?? undefined,
      })
      setResult({ ...result, change_request_id })
      await Promise.all([refetchCrs(), loadHistory()])
      toast.success(`Promoted to wiki page — ${change_request_id}`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setPromoting(false)
    }
  }

  async function removeHistory(id: number, e: React.MouseEvent) {
    e.stopPropagation()
    try {
      await api.deleteAskHistory(id)
      if (activeId === id) {
        setResult(null)
        setActiveId(null)
      }
      await loadHistory()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  async function clearHistory() {
    try {
      await api.clearAskHistory()
      setResult(null)
      setActiveId(null)
      await loadHistory()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  // honor ?q= from the command palette (ask once). Skip if we already have an
  // answer for that question in the store (restored after navigating back), so
  // returning to /ask?q=… doesn't re-run the query.
  useEffect(() => {
    const q = params.get("q")
    if (q && !askRef.current && !(result && question === q)) {
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
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-muted-foreground">
                {progress ? (PROGRESS_LABELS[progress] ?? progress) : "Thinking…"}
              </span>
              {jobId != null && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={cancelAsk}
                  className="h-7 gap-1.5 text-[12px] text-muted-foreground"
                >
                  <X className="size-3.5" /> Cancel
                </Button>
              )}
            </div>
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}

        {result && (
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Answer
              </span>
              {result.change_request_id ? (
                <span className="text-[12px] text-muted-foreground">
                  Promoted → {result.change_request_id}
                </span>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  disabled={promoting}
                  onClick={promote}
                >
                  <ArrowUpRight className="size-4" />
                  {promoting ? "Promoting…" : "Promote to wiki page"}
                </Button>
              )}
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
          </div>
        )}

        {history.length > 0 && (
          <>
            <hr className="my-5 border-border" />
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                History
              </span>
              <button
                onClick={clearHistory}
                className="flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
              >
                <Trash2 className="size-3" /> Clear
              </button>
            </div>
            <ul className="space-y-0.5">
              {history.map((h) => (
                <li
                  key={h.id}
                  className={`group flex items-center gap-2 rounded px-1.5 py-1 ${
                    activeId === h.id ? "bg-accent" : "hover:bg-accent/50"
                  }`}
                >
                  <button
                    onClick={() => openHistory(h)}
                    className="flex-1 truncate text-left text-[13px] text-muted-foreground hover:text-foreground"
                    title={h.question}
                  >
                    {h.question}
                    {h.change_request_id && (
                      <span className="ml-2 text-[11px] text-primary">↗ saved</span>
                    )}
                  </button>
                  <button
                    onClick={(e) => removeHistory(h.id, e)}
                    className="opacity-0 transition group-hover:opacity-100"
                    aria-label="Delete from history"
                  >
                    <X className="size-3.5 text-muted-foreground hover:text-destructive" />
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
