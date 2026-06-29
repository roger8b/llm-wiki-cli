import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  FileText,
  FileType,
  StickyNote,
  Upload,
  Plus,
  Search,
  RotateCw,
} from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { timeAgo } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Source, SourceContent, UrlPreview } from "@/types"
import { useIngestStore } from "@/stores/ingest"
import { useCrStore } from "@/stores/crs"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"

function sourceIcon(type: string) {
  if (type === "pdf") return <FileType className="size-5 text-rejected" />
  if (type === "text") return <StickyNote className="size-5 text-pending" />
  return <FileText className="size-5 text-primary" />
}

function statusBadge(status: Source["status"]) {
  const map: Record<string, string> = {
    processed: "bg-apply/10 text-apply border-apply/30",
    pending: "bg-pending/10 text-pending border-pending/30",
    processing: "bg-primary/10 text-primary border-primary/30",
    error: "bg-rejected/10 text-rejected border-rejected/30",
  }
  const label =
    status === "processed" ? "✓ ingested" : status === "pending" ? "⏳ pending" : status
  return (
    <span className={cn("rounded border px-1.5 py-px text-[10px]", map[status])}>
      {label}
    </span>
  )
}

/** Color tokens for the per-row status dot. Single source of truth — the badge
 *  palette above is the source; the dot uses the base color (`bg-apply`,
 *  `bg-pending`, `bg-primary`, `bg-rejected`) without the `/10` opacity so the
 *  dot stays opaque against any background. Re-exported for unit testing
 *  (#336). */
const STATUS_DOT_BG: Record<Source["status"], string> = {
  processed: "bg-apply",
  pending: "bg-pending",
  processing: "bg-primary",
  error: "bg-rejected",
}

/** Tailwind class for the per-row status dot. Processing pulses to signal a
 *  live ingest in another tab (#336 AC5). */
export function statusDotClass(status: Source["status"]): string {
  const base = "size-1.5 rounded-full shrink-0"
  const bg = STATUS_DOT_BG[status]
  const pulse = status === "processing" ? " animate-pulse" : ""
  return `${base} ${bg}${pulse}`
}

/** Human-readable label for the dot's native `title=` and ARIA `aria-label`.
 *  Kept short so the tooltip doesn't truncate (#336). */
export function statusDotLabel(status: Source["status"]): string {
  switch (status) {
    case "processed":
      return "Ingested"
    case "pending":
      return "Pending ingest"
    case "processing":
      return "Processing…"
    case "error":
      return "Last ingest failed"
  }
}

export function groupBySourceDir(sources: Source[]): Record<string, Source[]> {
  const groups: Record<string, Source[]> = {}
  for (const s of sources) {
    // raw/articles/x.md -> "articles"; raw/x.md -> "raw"
    const m = /^raw\/([^/]+)\//.exec(s.path)
    const dir = m ? m[1] : "raw"
    ;(groups[dir] ??= []).push(s)
  }
  return groups
}

/** Per-group source counts for the sidebar header breakdown (#337).
 *
 *  `pending` covers every non-processed status (pending / processing / error)
 *  so the header suffix honestly flags "this folder still needs action"
 *  regardless of why — including failed ingests. `processed` is exposed for
 *  future use (e.g. "5 ingested · 2 pending") but not rendered today. */
export function countByStatus(items: Source[]): {
  total: number
  pending: number
  processed: number
} {
  let processed = 0
  for (const s of items) if (s.status === "processed") processed++
  const total = items.length
  return { total, pending: total - processed, processed }
}

/** Chip filter selector (#338). The UI exposes 5 chips — one per concrete
 *  status plus an 'all' reset — so a user can drill into a specific bucket
 *  (e.g. "Error" only). Distinct from `countByStatus().pending`, which is the
 *  aggregate "still needs action" view used by the group header breakdown. */
export type StatusFilter = Source["status"] | "all"

export const STATUS_FILTERS: StatusFilter[] = [
  "all",
  "pending",
  "processing",
  "processed",
  "error",
]

export const STATUS_FILTER_LABELS: Record<StatusFilter, string> = {
  all: "All",
  pending: "Pending",
  processing: "Processing",
  processed: "Ingested",
  error: "Error",
}

/** Parse a deep-link `?status=…` param into a `StatusFilter`. Unknown values
 *  (including `null`/`undefined` when the param is missing) fall back to
 *  `'all'` so a malformed link never locks the user out of the list (#338
 *  AC3: default = current behavior). */
export function parseStatusFilter(raw: string | null | undefined): StatusFilter {
  if (raw && (STATUS_FILTERS as string[]).includes(raw)) {
    return raw as StatusFilter
  }
  return "all"
}

/** Apply the chip predicate. `'all'` is a no-op and returns the same array
 *  reference (no extra allocation) so `useMemo` can short-circuit. */
export function filterByStatus(
  items: Source[],
  filter: StatusFilter,
): Source[] {
  if (filter === "all") return items
  return items.filter((s) => s.status === filter)
}

/** Per-status counts for the chip row (#338 AC: stable when filter changes).
 *  Counts derive from the unfiltered list so chips don't dance as the user
 *  toggles filters. */
export function chipCounts(items: Source[]): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = {
    all: items.length,
    pending: 0,
    processing: 0,
    processed: 0,
    error: 0,
  }
  for (const s of items) counts[s.status]++
  return counts
}

/** Sources that still need an ingest action (#339 CTA). Same predicate as
 *  `countByStatus().pending`: every non-processed status counts as work to do
 *  (pending / processing / error). Exported for testing and for the bulk-ingest
 *  button in the sidebar header. */
export function pendingSources(items: Source[]): Source[] {
  return items.filter((s) => s.status !== "processed")
}

/** Same predicate as `pendingSources().length` — kept as a separate helper
 *  because call sites only need the count and the array allocation is wasted. */
export function pendingCount(items: Source[]): number {
  let n = 0
  for (const s of items) if (s.status !== "processed") n++
  return n
}

function AddSourceDialog({
  open,
  onOpenChange,
  onAdded,
  onAddedMany,
  initialTab = "file",
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onAdded: (s: Source, ingest: boolean) => void
  onAddedMany: (sources: Source[], ingest: boolean) => void
  initialTab?: "file" | "text" | "url"
}) {
  const [tab, setTab] = useState<"file" | "text" | "url">(initialTab)
  useEffect(() => {
    if (open) setTab(initialTab)
  }, [open, initialTab])
  const [dragover, setDragover] = useState(false)
  const [ingestNow, setIngestNow] = useState(true)
  const [busy, setBusy] = useState(false)
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
  const [url, setUrl] = useState("")
  const [preview, setPreview] = useState<UrlPreview | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return
      setBusy(true)
      try {
        const list = Array.from(files)
        const uploaded: Source[] = []
        const failed: string[] = []
        for (const f of list) {
          try {
            uploaded.push(await api.uploadSource(f))
          } catch (e) {
            failed.push(`${f.name}: ${(e as Error).message}`)
          }
        }
        if (failed.length) toast.error(`Upload failed — ${failed.join("; ")}`)
        if (uploaded.length === 1) onAdded(uploaded[0], ingestNow)
        else if (uploaded.length > 1) onAddedMany(uploaded, ingestNow)
        if (uploaded.length) onOpenChange(false)
      } finally {
        setBusy(false)
      }
    },
    [ingestNow, onAdded, onAddedMany, onOpenChange],
  )

  async function addText() {
    if (!title.trim() || !text.trim()) return
    setBusy(true)
    try {
      const src = await api.addTextSource(title, text)
      onAdded(src, ingestNow)
      onOpenChange(false)
      setTitle("")
      setText("")
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  async function previewUrl() {
    if (!url.trim()) return
    setBusy(true)
    setPreview(null)
    try {
      setPreview(await api.previewUrlSource(url.trim()))
    } catch (e) {
      toast.error(`Could not fetch: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  async function addUrl() {
    if (!url.trim()) return
    setBusy(true)
    try {
      const src = await api.addUrlSource(url.trim())
      if (src.already_present) toast.info("This article was already captured.")
      onAdded(src, ingestNow && !src.already_present)
      onOpenChange(false)
      setUrl("")
      setPreview(null)
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Add source</DialogTitle>
        </DialogHeader>

        <div className="flex gap-1 border-b">
          {(["file", "text", "url"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "border-b-2 border-transparent px-3 py-1.5 text-[13px] capitalize text-muted-foreground",
                tab === t && "border-b-primary font-medium text-primary",
              )}
            >
              {t === "file" ? "Upload file" : t === "text" ? "Paste text" : "From URL"}
            </button>
          ))}
        </div>

        {tab === "file" ? (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragover(true)
            }}
            onDragLeave={() => setDragover(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragover(false)
              handleFiles(e.dataTransfer.files)
            }}
            className={cn(
              "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed py-10 transition-colors",
              dragover ? "border-primary bg-primary/5" : "border-border",
            )}
          >
            <Upload className="size-7 text-muted-foreground" />
            <div className="text-[13px] font-medium">
              {busy ? "Uploading…" : "Drop files here or click to browse"}
            </div>
            <div className="text-[11px] text-muted-foreground">
              Supports .md .pdf .txt .html
            </div>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".md,.pdf,.txt,.html"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </button>
        ) : tab === "text" ? (
          <div className="space-y-2">
            <Input
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <Textarea
              placeholder="Paste your note / article text…"
              className="min-h-[140px]"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
        ) : (
          <div className="space-y-2 min-w-0">
            <div className="flex gap-2 min-w-0">
              <Input
                className="min-w-0 flex-1"
                placeholder="https://example.com/article"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value)
                  setPreview(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    previewUrl()
                  }
                }}
              />
              <Button
                variant="secondary"
                onClick={previewUrl}
                disabled={busy || !url.trim()}
              >
                {busy ? "Fetching…" : "Preview"}
              </Button>
            </div>
            {preview && (
              <div className="rounded-md border bg-muted/40 p-3 text-[12px]">
                <div className="font-medium text-foreground">
                  {preview.title || "(untitled)"}
                </div>
                {(preview.author || preview.date) && (
                  <div className="mt-0.5 text-muted-foreground">
                    {[preview.author, preview.date].filter(Boolean).join(" · ")}
                  </div>
                )}
                <div className="mt-2 max-h-40 overflow-y-auto rounded-sm bg-background/50 p-2 text-muted-foreground">
                  <MarkdownReader content={preview.preview} className="text-[12px] leading-snug" />
                </div>
              </div>
            )}
          </div>
        )}

        <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Checkbox
            checked={ingestNow}
            onCheckedChange={(v) => setIngestNow(Boolean(v))}
          />
          Ingest immediately after adding (recommended)
        </label>

        {tab === "text" && (
          <div className="flex justify-end">
            <Button onClick={addText} disabled={busy || !title.trim() || !text.trim()}>
              Add & {ingestNow ? "Ingest" : "Save"} →
            </Button>
          </div>
        )}

        {tab === "url" && (
          <div className="flex justify-end">
            <Button onClick={addUrl} disabled={busy || !url.trim()}>
              Capture & {ingestNow ? "Ingest" : "Save"} →
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function SourcesView() {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [filter, setFilter] = useState("")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState<SourceContent | null>(null)
  const [contentLoading, setContentLoading] = useState(false)
  const [contentError, setContentError] = useState<string | null>(null)
  const runIngest = useIngestStore((s) => s.run)
  const runBatch = useIngestStore((s) => s.runBatch)
  // Live ingest state for the bulk-CTA button (#339): disable while running
  // and show the done/total counter so the user sees progress without staring
  // at the drawer. `items` belongs to the most recent batch (cleared on close).
  const ingestStatus = useIngestStore((s) => s.status)
  const ingestItems = useIngestStore((s) => s.items)
  const refetchCrs = useCrStore((s) => s.fetch)

  const openSource = useCallback(async (path: string) => {
    setSelected(path)
    setContent(null)
    setContentError(null)
    setContentLoading(true)
    try {
      setContent(await api.getSourceContent(path))
    } catch (e) {
      setContentError((e as Error).message)
    } finally {
      setContentLoading(false)
    }
  }, [])

  const [params, setParams] = useSearchParams()
  const [addTab, setAddTab] = useState<"file" | "text" | "url">("file")

  // Deep-link: ?add=url (from the command palette) opens the URL capture tab.
  useEffect(() => {
    const add = params.get("add")
    if (!add) return
    setAddTab(add === "url" || add === "text" ? add : "file")
    setDialogOpen(true)
    const next = new URLSearchParams(params)
    next.delete("add")
    setParams(next, { replace: true })
  }, [params, setParams])

  // Deep-link: ?status=pending (or any StatusFilter) pre-selects the chip on
  // load. Aligned with the `?add=` and `?path=` deep-links above (#338).
  useEffect(() => {
    const raw = params.get("status")
    if (raw === null) return
    setStatusFilter(parseStatusFilter(raw))
    const next = new URLSearchParams(params)
    next.delete("status")
    setParams(next, { replace: true })
  }, [params, setParams])

  const load = useCallback(
    async (selectFirst = false) => {
      setLoading(true)
      try {
        const list = await api.listSources()
        setSources(list)
        // Deep-link: ?path=raw/... opens that source directly (#192 citations).
        const wanted = params.get("path")
        if (wanted && list.some((s) => s.path === wanted)) openSource(wanted)
        else if (selectFirst && list[0]) openSource(list[0].path)
      } catch (e) {
        toast.error((e as Error).message)
      } finally {
        setLoading(false)
      }
    },
    [openSource, params],
  )

  useEffect(() => {
    load(true)
  }, [load])

  const ingest = useCallback(
    async (source: Source) => {
      await runIngest(`Ingesting ${source.path.split("/").pop()}`, () =>
        api.ingestSource(source.path),
      )
      await Promise.all([load(), refetchCrs()])
    },
    [runIngest, load, refetchCrs],
  )

  // Re-ingest = "run the agent again on the same source" (force=True bypasses
  // the content-hash dedup). Use after the wiki/model/skills have changed, or
  // when a previous run produced an empty CR (#237 follow-up).
  const reIngest = useCallback(
    async (source: Source) => {
      await runIngest(`Re-ingest ${source.path.split("/").pop()}`, () =>
        api.ingestSource(source.path, /* force */ true),
      )
      await Promise.all([load(), refetchCrs()])
    },
    [runIngest, load, refetchCrs],
  )

  const ingestMany = useCallback(
    async (srcs: Source[]) => {
      await runBatch(
        srcs.map((s) => ({ name: s.path.split("/").pop() || s.path, path: s.path })),
        (paths) => api.ingestSources(paths),
      )
      await Promise.all([load(), refetchCrs()])
    },
    [runBatch, load, refetchCrs],
  )

  const filtered = useMemo(
    () => {
      const byStatus = filterByStatus(sources, statusFilter)
      if (!filter) return byStatus
      const q = filter.toLowerCase()
      return byStatus.filter(
        (s) =>
          s.path.toLowerCase().includes(q) ||
          (s.title ?? "").toLowerCase().includes(q),
      )
    },
    [sources, filter, statusFilter],
  )
  const counts = useMemo(() => chipCounts(sources), [sources])
  const pendingItems = useMemo(() => pendingSources(sources), [sources])
  const groups = useMemo(() => groupBySourceDir(filtered), [filtered])

  // Live batch progress for the bulk-CTA button (#339). Done count comes from
  // the current batch items (set to queued at runBatch start); falls back to
  // 0 if no batch is active.
  const batchDone = useMemo(
    () => ingestItems.filter((i) => i.status === "done").length,
    [ingestItems],
  )
  const isIngesting = ingestStatus === "running"
  const current = sources.find((s) => s.path === selected) ?? null

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* file list */}
      <aside className="flex w-[260px] shrink-0 flex-col overflow-hidden border-r-[1.5px]">
        <div className="shrink-0 space-y-2 border-b-[1.5px] p-2">
          <Button
            onClick={() => setDialogOpen(true)}
            size="sm"
            className="w-full gap-1.5"
          >
            <Plus className="size-4" /> Add source
          </Button>
          {pendingItems.length > 0 && (
            <Button
              onClick={() => ingestMany(pendingItems)}
              disabled={isIngesting}
              size="sm"
              variant="outline"
              className="w-full gap-1.5"
              title={
                isIngesting
                  ? `Running ${batchDone}/${pendingItems.length}…`
                  : `Ingest ${pendingItems.length} pending source${pendingItems.length === 1 ? "" : "s"}`
              }
            >
              <RotateCw className={cn("size-4", isIngesting && "animate-spin")} />
              {isIngesting
                ? `Running ${batchDone}/${pendingItems.length}…`
                : `Ingest ${pendingItems.length} pending →`}
            </Button>
          )}
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
            {STATUS_FILTERS.map((sf) => {
              const active = statusFilter === sf
              return (
                <button
                  key={sf}
                  onClick={() => setStatusFilter(sf)}
                  aria-pressed={active}
                  className={cn(
                    "h-6 rounded border px-1.5 text-[11px] transition-colors",
                    active
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  {STATUS_FILTER_LABELS[sf]} ({counts[sf]})
                </button>
              )
            })}
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter sources…"
              className="h-8 pl-7 text-[13px]"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {Object.entries(groups).map(([dir, items]) => {
            const { total, pending } = countByStatus(items)
            return (
              <div key={dir}>
                <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {dir} ({total}
                  {pending > 0 && (
                    <span className="text-pending font-normal normal-case">
                      {" "}· {pending} pending
                    </span>
                  )}
                  )
                </div>
              {items.map((s) => (
                <button
                  key={s.path}
                  onClick={() => openSource(s.path)}
                  className={cn(
                    "flex w-full items-center gap-1.5 px-2 py-1 pl-3 text-left text-[12.5px] transition-colors hover:bg-accent",
                    selected === s.path && "bg-accent font-medium text-primary",
                  )}
                  title={statusDotLabel(s.status)}
                  aria-label={`${s.path.split("/").pop()} — ${statusDotLabel(s.status)}`}
                >
                  <span
                    className={statusDotClass(s.status)}
                    aria-hidden="true"
                  />
                  <span className="shrink-0">{sourceIcon(s.type)}</span>
                  <span className="truncate">{s.path.split("/").pop()}</span>
                </button>
              ))}
            </div>
            )
          })}
          {!loading && sources.length === 0 && (
            <div className="px-3 py-3 text-[12px] text-muted-foreground">
              No sources yet. Add one to get started.
            </div>
          )}
          {!loading && sources.length > 0 && filtered.length === 0 && (
            <div className="px-3 py-3 text-[12px] text-muted-foreground">
              No sources match the current filter.{" "}
              <button
                onClick={() => {
                  setStatusFilter("all")
                  setFilter("")
                }}
                className="text-primary underline-offset-2 hover:underline"
              >
                Reset filters
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* reader */}
      <section className="flex-1 overflow-y-auto">
        {current ? (
          <div className="mx-auto max-w-[760px] p-6">
            <div className="mb-4 flex items-start justify-between gap-3 rounded-lg border bg-card px-4 py-2.5 text-[12px] text-muted-foreground">
              <div className="min-w-0">
                <span className="font-mono">{current.path}</span>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                  <span>SHA {current.hash.slice(0, 6)}</span>
                  <span>{timeAgo(current.added_at)}</span>
                  {statusBadge(current.status)}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 gap-1.5"
                onClick={() =>
                  current.status === "processed" ? reIngest(current) : ingest(current)
                }
              >
                <RotateCw className="size-3.5" />
                {current.status === "processed" ? "Re-ingest" : "Ingest"}
              </Button>
            </div>

            {contentLoading ? (
              <div className="text-[13px] text-muted-foreground">Loading…</div>
            ) : contentError ? (
              <div className="rounded-lg border border-dashed py-8 text-center text-[13px] text-rejected">
                {contentError}
              </div>
            ) : content ? (
              content.type === "md" ? (
                <MarkdownReader content={content.content} />
              ) : (
                <>
                  {content.type !== "text" && (
                    <div className="mb-2 text-[11px] text-muted-foreground">
                      Textual representation of a {content.type} source.
                    </div>
                  )}
                  <pre className="whitespace-pre-wrap break-words rounded-lg border bg-card p-4 text-[12.5px]">
                    {content.content}
                  </pre>
                </>
              )
            ) : null}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
            {loading ? "Loading…" : "Select a source"}
          </div>
        )}
      </section>

      <AddSourceDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initialTab={addTab}
        onAdded={(src, doIngest) => {
          load()
          if (doIngest) ingest(src)
          else toast.success(`Added ${src.path.split("/").pop()}`)
        }}
        onAddedMany={(srcs, doIngest) => {
          load()
          if (doIngest) ingestMany(srcs)
          else toast.success(`Added ${srcs.length} sources`)
        }}
      />
    </div>
  )
}
