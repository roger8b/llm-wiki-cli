import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { Sparkles, Send, ArrowUpRight, Trash2, X, Plus } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { AskHistoryItem, QueryResult } from "@/types"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import { CitationList } from "@/components/shared/CitationList"
import { IndeterminateBar } from "@/components/shared/IndeterminateBar"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { useCrStore } from "@/stores/crs"
import { useAskStore, type AskTurn } from "@/stores/ask"

const SUGGESTED = [
  "What are the trade-offs of RAG vs fine-tuning?",
  "How does attention work?",
  "What is chunking?",
]

// Group flat history rows into conversations. Rows sharing a conversation_id
// form one thread (title = its first question); legacy rows (no id) each stand
// alone. Newest conversation first.
interface Conversation {
  id: string | null
  key: string
  title: string
  items: AskHistoryItem[]
}

function groupConversations(history: AskHistoryItem[]): Conversation[] {
  const byKey = new Map<string, AskHistoryItem[]>()
  for (const item of history) {
    const key = item.conversation_id ?? `legacy-${item.id}`
    const list = byKey.get(key) ?? []
    list.push(item)
    byKey.set(key, list)
  }
  const convos: Conversation[] = []
  for (const [key, items] of byKey) {
    const ordered = [...items].sort((a, b) => a.id - b.id) // chronological
    convos.push({
      id: ordered[0].conversation_id ?? null,
      key,
      title: ordered[0].question,
      items: ordered,
    })
  }
  // Most recently active conversation first (highest last-item id).
  convos.sort((a, b) => b.items[b.items.length - 1].id - a.items[a.items.length - 1].id)
  return convos
}

const itemToTurn = (item: AskHistoryItem): AskTurn => ({
  question: item.question,
  result: {
    answer: item.answer,
    citations: item.citations,
    change_request_id: item.change_request_id,
  },
  historyId: item.id,
})

export function AskView() {
  const navigate = useNavigate()
  const question = useAskStore((s) => s.question)
  const setQuestion = useAskStore((s) => s.setQuestion)
  const turns = useAskStore((s) => s.turns)
  const addTurn = useAskStore((s) => s.addTurn)
  const conversationId = useAskStore((s) => s.conversationId)
  const setConversationId = useAskStore((s) => s.setConversationId)
  const newConversation = useAskStore((s) => s.newConversation)
  const loadConversation = useAskStore((s) => s.loadConversation)
  const loading = useAskStore((s) => s.loading)
  const setLoading = useAskStore((s) => s.setLoading)

  const [save, setSave] = useState(false)
  const [promotingIdx, setPromotingIdx] = useState<number | null>(null)
  const [history, setHistory] = useState<AskHistoryItem[]>([])
  const [jobId, setJobId] = useState<number | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const refetchCrs = useCrStore((s) => s.fetch)
  const [params] = useSearchParams()
  const askRef = useRef(false)
  const threadEndRef = useRef<HTMLDivElement>(null)

  const conversations = useMemo(() => groupConversations(history), [history])

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

  // Keep the latest turn / loading indicator in view.
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [turns.length, loading])

  async function ask(q: string) {
    const query = q.trim()
    if (!query) return
    setLoading(true)
    setPendingQuestion(query)
    setQuestion("")
    setProgress(null)
    try {
      const startRes = await api.ask(query, save, conversationId)
      const startedJobId = (startRes as { job_id?: number }).job_id
      if (typeof startedJobId !== "number") {
        toast.error("Backend did not queue the question")
        return
      }
      setJobId(startedJobId)
      await api.streamJob(startedJobId, {
        onProgress: (step) => setProgress(step),
        onResult: async (result) => {
          if (!result) {
            toast.error("No result returned from job")
            return
          }
          const res = JSON.parse(result) as QueryResult
          addTurn({ question: query, result: res, historyId: res.history_id ?? null })
          if (res.conversation_id) setConversationId(res.conversation_id)
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
      setPendingQuestion(null)
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

  async function promote(idx: number) {
    const turn = turns[idx]
    if (!turn) return
    setPromotingIdx(idx)
    try {
      const { change_request_id } = await api.promoteAnswer({
        question: turn.question.trim(),
        answer: turn.result.answer,
        history_id: turn.historyId ?? undefined,
      })
      // Replace the turn with the promoted CR id.
      const next = [...turns]
      next[idx] = { ...turn, result: { ...turn.result, change_request_id } }
      useAskStore.setState({ turns: next })
      await Promise.all([refetchCrs(), loadHistory()])
      toast.success(`Promoted to wiki page — ${change_request_id}`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setPromotingIdx(null)
    }
  }

  async function removeConversation(c: Conversation, e: React.MouseEvent) {
    e.stopPropagation()
    try {
      await Promise.all(c.items.map((i) => api.deleteAskHistory(i.id)))
      if (conversationId && c.id === conversationId) newConversation()
      await loadHistory()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  async function clearHistory() {
    try {
      await api.clearAskHistory()
      newConversation()
      await loadHistory()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  // honor ?q= from the command palette (ask once into a fresh conversation).
  useEffect(() => {
    const q = params.get("q")
    if (q && !askRef.current) {
      askRef.current = true
      newConversation()
      ask(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const showSuggested = turns.length === 0 && !loading

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[760px]">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold">
            <Sparkles className="size-5 text-primary" /> Ask the wiki
          </h1>
          {turns.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={newConversation}
              disabled={loading}
            >
              <Plus className="size-4" /> New conversation
            </Button>
          )}
        </div>

        {/* Conversation thread */}
        <div className="space-y-6">
          {turns.map((turn, idx) => (
            <div key={idx} className="space-y-2">
              <div className="rounded-lg bg-accent/60 px-3 py-2 text-[14px] font-medium">
                {turn.question}
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Answer
                  </span>
                  {turn.result.change_request_id ? (
                    <span className="text-[12px] text-muted-foreground">
                      Promoted → {turn.result.change_request_id}
                    </span>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      disabled={promotingIdx === idx}
                      onClick={() => promote(idx)}
                    >
                      <ArrowUpRight className="size-4" />
                      {promotingIdx === idx ? "Promoting…" : "Promote to wiki page"}
                    </Button>
                  )}
                </div>
                <MarkdownReader
                  content={turn.result.answer}
                  onWikiLink={(t) => navigate(`/wiki?q=${encodeURIComponent(t)}`)}
                />
                <CitationList citations={turn.result.citations} />
              </div>
            </div>
          ))}

          {loading && (
            <div className="space-y-3">
              {pendingQuestion && (
                <div className="rounded-lg bg-accent/60 px-3 py-2 text-[14px] font-medium">
                  {pendingQuestion}
                </div>
              )}
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
              <IndeterminateBar />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
          <div ref={threadEndRef} />
        </div>

        {turns.length > 0 && <hr className="my-5 border-border" />}

        {/* Composer */}
        <div className="flex gap-2">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") ask(question)
            }}
            placeholder={
              turns.length > 0
                ? "Ask a follow-up…  (⌘↵ to send)"
                : "Ask a question grounded in your wiki…  (⌘↵ to send)"
            }
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

        {showSuggested && (
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTED.map((s) => (
              <button
                key={s}
                onClick={() => ask(s)}
                className="rounded-full border bg-card px-3 py-1 text-[12px] text-muted-foreground hover:border-primary hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {conversations.length > 0 && (
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
              {conversations.map((c) => (
                <li
                  key={c.key}
                  className={`group flex items-center gap-2 rounded px-1.5 py-1 ${
                    conversationId && c.id === conversationId
                      ? "bg-accent"
                      : "hover:bg-accent/50"
                  }`}
                >
                  <button
                    onClick={() => loadConversation(c.id, c.items.map(itemToTurn))}
                    className="flex-1 truncate text-left text-[13px] text-muted-foreground hover:text-foreground"
                    title={c.title}
                  >
                    {c.title}
                    {c.items.length > 1 && (
                      <span className="ml-2 text-[11px] text-muted-foreground">
                        · {c.items.length} turns
                      </span>
                    )}
                    {c.items.some((i) => i.change_request_id) && (
                      <span className="ml-2 text-[11px] text-primary">↗ saved</span>
                    )}
                  </button>
                  <button
                    onClick={(e) => removeConversation(c, e)}
                    className="opacity-0 transition group-hover:opacity-100"
                    aria-label="Delete conversation"
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
