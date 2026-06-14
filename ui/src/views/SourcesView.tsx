import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
import type { Source, SourceContent } from "@/types"
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

function AddSourceDialog({
  open,
  onOpenChange,
  onAdded,
  onAddedMany,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onAdded: (s: Source, ingest: boolean) => void
  onAddedMany: (sources: Source[], ingest: boolean) => void
}) {
  const [tab, setTab] = useState<"file" | "text">("file")
  const [dragover, setDragover] = useState(false)
  const [ingestNow, setIngestNow] = useState(true)
  const [busy, setBusy] = useState(false)
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Add source</DialogTitle>
        </DialogHeader>

        <div className="flex gap-1 border-b">
          {(["file", "text"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "border-b-2 border-transparent px-3 py-1.5 text-[13px] capitalize text-muted-foreground",
                tab === t && "border-b-primary font-medium text-primary",
              )}
            >
              {t === "file" ? "Upload file" : "Paste text"}
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
        ) : (
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
      </DialogContent>
    </Dialog>
  )
}

export function SourcesView() {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [filter, setFilter] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState<SourceContent | null>(null)
  const [contentLoading, setContentLoading] = useState(false)
  const [contentError, setContentError] = useState<string | null>(null)
  const runIngest = useIngestStore((s) => s.run)
  const runBatch = useIngestStore((s) => s.runBatch)
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

  const load = useCallback(
    async (selectFirst = false) => {
      setLoading(true)
      try {
        const list = await api.listSources()
        setSources(list)
        if (selectFirst && list[0]) openSource(list[0].path)
      } catch (e) {
        toast.error((e as Error).message)
      } finally {
        setLoading(false)
      }
    },
    [openSource],
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
    () =>
      filter
        ? sources.filter(
            (s) =>
              s.path.toLowerCase().includes(filter.toLowerCase()) ||
              (s.title ?? "").toLowerCase().includes(filter.toLowerCase()),
          )
        : sources,
    [sources, filter],
  )
  const groups = useMemo(() => groupBySourceDir(filtered), [filtered])
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
          {Object.entries(groups).map(([dir, items]) => (
            <div key={dir}>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {dir} ({items.length})
              </div>
              {items.map((s) => (
                <button
                  key={s.path}
                  onClick={() => openSource(s.path)}
                  className={cn(
                    "flex w-full items-center gap-1.5 px-2 py-1 pl-3 text-left text-[12.5px] transition-colors hover:bg-accent",
                    selected === s.path && "bg-accent font-medium text-primary",
                  )}
                >
                  <span className="shrink-0">{sourceIcon(s.type)}</span>
                  <span className="truncate">{s.path.split("/").pop()}</span>
                </button>
              ))}
            </div>
          ))}
          {!loading && sources.length === 0 && (
            <div className="px-3 py-3 text-[12px] text-muted-foreground">
              No sources yet. Add one to get started.
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
