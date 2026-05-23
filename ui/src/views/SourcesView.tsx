import { useCallback, useEffect, useRef, useState } from "react"
import { FileText, FileType, StickyNote, Upload, Plus } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { timeAgo } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Source } from "@/types"
import { useIngestStore } from "@/stores/ingest"
import { useCrStore } from "@/stores/crs"
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

function SourceCard({ source, onIngest }: { source: Source; onIngest: (s: Source) => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border bg-card px-4 py-3">
      <div className="mt-0.5">{sourceIcon(source.type)}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">
          {source.path.split("/").pop()}
        </div>
        {source.title && (
          <div className="truncate text-[12px] text-muted-foreground">
            {source.title}
          </div>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          {source.path.replace(/[^/]+$/, "")}
          <span>·</span>
          SHA {source.hash.slice(0, 6)}
          <span>·</span>
          {timeAgo(source.added_at)}
          <span>·</span>
          {statusBadge(source.status)}
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={() => onIngest(source)}>
        {source.status === "processed" ? "Re-ingest" : "Ingest"}
      </Button>
    </div>
  )
}

function AddSourceDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onAdded: (s: Source, ingest: boolean) => void
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
        const src = await api.uploadSource(files[0])
        onAdded(src, ingestNow)
        onOpenChange(false)
      } catch (e) {
        toast.error(`Upload failed: ${(e as Error).message}`)
      } finally {
        setBusy(false)
      }
    },
    [ingestNow, onAdded, onOpenChange],
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
              {busy ? "Uploading…" : "Drop a file here or click to browse"}
            </div>
            <div className="text-[11px] text-muted-foreground">
              Supports .md .pdf .txt .html
            </div>
            <input
              ref={fileRef}
              type="file"
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
  const runIngest = useIngestStore((s) => s.run)
  const refetchCrs = useCrStore((s) => s.fetch)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setSources(await api.listSources())
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
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

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[820px]">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="font-display text-lg font-semibold">Sources</h1>
          <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
            <Plus className="size-4" /> Add source
          </Button>
        </div>

        {loading ? (
          <div className="text-[13px] text-muted-foreground">Loading…</div>
        ) : sources.length === 0 ? (
          <div className="rounded-lg border border-dashed py-12 text-center text-[13px] text-muted-foreground">
            No sources yet. Add one to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {sources.map((s) => (
              <SourceCard key={s.path} source={s} onIngest={ingest} />
            ))}
          </div>
        )}
      </div>

      <AddSourceDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onAdded={(src, doIngest) => {
          load()
          if (doIngest) ingest(src)
          else toast.success(`Added ${src.path.split("/").pop()}`)
        }}
      />
    </div>
  )
}
