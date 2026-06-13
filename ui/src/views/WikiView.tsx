import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronRight, FileText, Search, Trash2, Link2, Pencil, Plus } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { timeAgo } from "@/lib/format"
import type { PageDetail, PageMeta, PageType } from "@/types"
import { pagePath } from "@/lib/slug"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import { PageEditor } from "@/components/shared/PageEditor"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useCrStore } from "@/stores/crs"

interface Backlink {
  path: string
  title: string
}

/** A page open in the editor: an existing edit (#186) or a new creation (#187). */
interface EditorDraft {
  detail: PageDetail
  isNew: boolean
}

function groupByDir(pages: PageMeta[]): Record<string, PageMeta[]> {
  const groups: Record<string, PageMeta[]> = {}
  for (const p of pages) {
    const m = /^wiki\/([^/]+)\//.exec(p.path)
    const dir = m ? m[1] : "other"
    ;(groups[dir] ??= []).push(p)
  }
  return groups
}

export function WikiView() {
  const [pages, setPages] = useState<PageMeta[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<PageDetail | null>(null)
  const [filter, setFilter] = useState("")
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [params] = useSearchParams()
  const refetchCrs = useCrStore((s) => s.fetch)

  // delete-page dialog state
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [backlinks, setBacklinks] = useState<Backlink[]>([])
  const [deleting, setDeleting] = useState(false)

  // editor state (#186 edit / #187 new): a draft page + whether it's a creation.
  const [editorDraft, setEditorDraft] = useState<EditorDraft | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [newPageOpen, setNewPageOpen] = useState(false)

  // title → path map for wikilink resolution
  const titleMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const p of pages) m.set(p.title.toLowerCase(), p.path)
    return m
  }, [pages])
  const titles = useMemo(() => pages.map((p) => p.title), [pages])

  async function handleProposeEdit(
    frontmatter: Record<string, unknown>,
    body: string,
  ) {
    if (!editorDraft) return
    setSavingEdit(true)
    try {
      const { change_request_id } = await api.proposeEdit(
        editorDraft.detail.path,
        frontmatter,
        body,
        editorDraft.isNew,
      )
      await refetchCrs()
      toast.success(`Proposed as ${change_request_id} — review to apply`)
      setEditorDraft(null)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSavingEdit(false)
    }
  }

  // Build a draft from a type template and open the editor in "create" mode.
  async function startNewPage(type: PageType, title: string, tags: string[]) {
    const path = pagePath(type, title)
    let body = `# ${title}\n`
    try {
      const templates = await api.listTemplates()
      const tmpl = templates.find((t) => t.type === type)?.body
      if (tmpl) body = tmpl.replaceAll("{{title}}", title)
    } catch {
      // fall back to a minimal body if templates can't be loaded
    }
    setEditorDraft({
      detail: {
        path,
        frontmatter: { title, type, tags, confidence: "medium", sources: [] },
        body,
      },
      isNew: true,
    })
    setNewPageOpen(false)
  }

  const openPath = useCallback(async (path: string) => {
    setSelected(path)
    setBacklinks([])
    setEditorDraft(null)
    try {
      setDetail(await api.getPage(path))
    } catch (e) {
      toast.error((e as Error).message)
      return
    }
    try {
      // Powers the "Linked from" panel and the delete dialog's impact preview.
      setBacklinks((await api.backlinks(path)).backlinks)
    } catch {
      // backlinks are best-effort
    }
  }, [])

  useEffect(() => {
    api
      .listPages()
      .then((p) => {
        setPages(p)
        // honor ?q=Title from Ask wikilinks, else open first page
        const q = params.get("q")?.toLowerCase()
        const match = q ? p.find((x) => x.title.toLowerCase() === q) : undefined
        const target = match ?? p[0]
        if (target) openPath(target.path)
      })
      .catch((e) => toast.error((e as Error).message))
    // ⌘K "New wiki page" routes here with ?new=1 (#187).
    if (params.get("new")) setNewPageOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function onWikiLink(title: string) {
    const path = titleMap.get(title.toLowerCase())
    if (path) openPath(path)
    else toast(`No page titled "${title}" yet`)
  }

  function openDeleteDialog() {
    if (!detail) return
    // backlinks for the open page are already loaded by openPath.
    setDeleteOpen(true)
  }

  async function confirmDelete(unlinkBacklinks: boolean) {
    if (!detail) return
    setDeleting(true)
    try {
      const { change_request_id } = await api.deletePage(
        detail.path,
        unlinkBacklinks,
      )
      await refetchCrs()
      toast.success(`Deletion proposed — review ${change_request_id} to apply`)
      setDeleteOpen(false)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  const filtered = filter
    ? pages.filter(
        (p) =>
          p.title.toLowerCase().includes(filter.toLowerCase()) ||
          p.path.toLowerCase().includes(filter.toLowerCase()),
      )
    : pages
  const groups = groupByDir(filtered)
  const fm = detail?.frontmatter ?? {}

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* tree */}
      <aside className="flex w-[260px] shrink-0 flex-col overflow-hidden border-r-[1.5px]">
        <div className="shrink-0 space-y-2 border-b-[1.5px] p-2">
          <Button
            size="sm"
            className="w-full gap-1.5"
            onClick={() => setNewPageOpen(true)}
          >
            <Plus className="size-4" /> New page
          </Button>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter pages…"
              className="h-8 pl-7 text-[13px]"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {Object.entries(groups).map(([dir, items]) => {
            const isCollapsed = collapsed.has(dir)
            return (
              <div key={dir}>
                <button
                  onClick={() =>
                    setCollapsed((s) => {
                      const n = new Set(s)
                      if (n.has(dir)) n.delete(dir)
                      else n.add(dir)
                      return n
                    })
                  }
                  className="flex w-full items-center gap-1 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  <ChevronRight
                    className={cn(
                      "size-3 transition-transform",
                      !isCollapsed && "rotate-90",
                    )}
                  />
                  {dir} ({items.length})
                </button>
                {!isCollapsed &&
                  items.map((p) => (
                    <button
                      key={p.path}
                      onClick={() => openPath(p.path)}
                      className={cn(
                        "flex w-full items-center gap-1.5 px-2 py-1 pl-6 text-left text-[12.5px] transition-colors hover:bg-accent",
                        selected === p.path &&
                          "bg-accent font-medium text-primary",
                      )}
                    >
                      <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{p.title}</span>
                    </button>
                  ))}
              </div>
            )
          })}
          {pages.length === 0 && (
            <div className="px-3 py-3 text-[12px] text-muted-foreground">
              No pages yet.
            </div>
          )}
        </div>
      </aside>

      {/* reader / editor */}
      <section className="flex-1 overflow-y-auto">
        {editorDraft ? (
          <div className="mx-auto max-w-[900px] p-6">
            <div className="mb-3 font-mono text-[12px] text-muted-foreground">
              {editorDraft.isNew ? "New page" : "Editing"}: {editorDraft.detail.path}
            </div>
            <div className="flex h-[calc(100vh-160px)] min-h-[420px] flex-col">
              <PageEditor
                detail={editorDraft.detail}
                titles={titles}
                saving={savingEdit}
                onSave={handleProposeEdit}
                onCancel={() => setEditorDraft(null)}
              />
            </div>
          </div>
        ) : detail ? (
          <div className="mx-auto max-w-[760px] p-6">
            <div className="mb-4 flex items-start justify-between gap-3 rounded-lg border bg-card px-4 py-2.5 text-[12px] text-muted-foreground">
              <div className="min-w-0">
                <span className="font-mono">{detail.path}</span>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                  {fm.type ? <span>type: {String(fm.type)}</span> : null}
                  {fm.confidence ? (
                    <span>confidence: {String(fm.confidence)}</span>
                  ) : null}
                  {fm.updated_at ? (
                    <span>updated: {timeAgo(String(fm.updated_at))}</span>
                  ) : null}
                  {Array.isArray(fm.tags) && fm.tags.length > 0 ? (
                    <span>tags: {(fm.tags as string[]).join(", ")}</span>
                  ) : null}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1.5 text-muted-foreground hover:text-foreground"
                  onClick={() => setEditorDraft({ detail, isNew: false })}
                >
                  <Pencil className="size-4" /> Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1.5 text-muted-foreground hover:text-destructive"
                  onClick={openDeleteDialog}
                >
                  <Trash2 className="size-4" /> Delete
                </Button>
              </div>
            </div>
            <MarkdownReader content={detail.body} onWikiLink={onWikiLink} />

            {backlinks.length > 0 && (
              <div className="mt-6 rounded-lg border bg-card p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <Link2 className="size-3.5" /> Linked from
                </div>
                <ul className="space-y-0.5">
                  {backlinks.map((b) => (
                    <li key={b.path}>
                      <button
                        onClick={() => openPath(b.path)}
                        className="text-left text-[13px] text-primary hover:underline"
                        title={b.path}
                      >
                        {b.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
            Select a page
          </div>
        )}
      </section>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete “{detail?.frontmatter?.title ? String(detail.frontmatter.title) : detail?.path}”?</DialogTitle>
            <DialogDescription>
              Deletion is proposed as a change request — nothing is removed until
              you apply it in Review.
            </DialogDescription>
          </DialogHeader>

          {backlinks.length > 0 ? (
            <div className="rounded-md border bg-muted/40 p-3 text-[13px]">
              <div className="mb-1.5 flex items-center gap-1.5 font-medium text-foreground">
                <Link2 className="size-3.5" />
                {backlinks.length} page{backlinks.length > 1 ? "s" : ""} link
                {backlinks.length > 1 ? "" : "s"} here
              </div>
              <ul className="max-h-40 space-y-0.5 overflow-y-auto">
                {backlinks.map((b) => (
                  <li key={b.path} className="truncate text-muted-foreground" title={b.path}>
                    · {b.title}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              No other pages link to this one.
            </p>
          )}

          <DialogFooter className="gap-2 sm:justify-end">
            {backlinks.length > 0 ? (
              <>
                <Button
                  variant="outline"
                  disabled={deleting}
                  onClick={() => confirmDelete(false)}
                >
                  Delete &amp; keep references
                </Button>
                <Button
                  variant="destructive"
                  disabled={deleting}
                  onClick={() => confirmDelete(true)}
                >
                  Delete &amp; unlink references
                </Button>
              </>
            ) : (
              <Button
                variant="destructive"
                disabled={deleting}
                onClick={() => confirmDelete(false)}
              >
                {deleting ? "Proposing…" : "Delete page"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <NewPageDialog
        open={newPageOpen}
        onOpenChange={setNewPageOpen}
        pages={pages}
        onCreate={startNewPage}
        onOpenExisting={openPath}
      />
    </div>
  )
}

const NEW_PAGE_TYPES: PageType[] = [
  "concept",
  "entity",
  "source_summary",
  "synthesis",
  "decision",
  "project",
  "research",
]

function NewPageDialog({
  open,
  onOpenChange,
  pages,
  onCreate,
  onOpenExisting,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  pages: PageMeta[]
  onCreate: (type: PageType, title: string, tags: string[]) => void
  onOpenExisting: (path: string) => void
}) {
  const [type, setType] = useState<PageType>("concept")
  const [title, setTitle] = useState("")
  const [tagsRaw, setTagsRaw] = useState("")

  const path = title.trim() ? pagePath(type, title) : ""
  const collision = path ? pages.find((p) => p.path === path) : undefined
  const valid = title.trim().length > 0 && !collision

  function reset() {
    setType("concept")
    setTitle("")
    setTagsRaw("")
  }
  function confirm() {
    if (!valid) return
    const tags = tagsRaw.split(/[,\s]+/).filter(Boolean)
    onCreate(type, title.trim(), tags)
    reset()
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset()
        onOpenChange(v)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New wiki page</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
            Type
            <select
              value={type}
              onChange={(e) => setType(e.target.value as PageType)}
              className="h-9 rounded-md border bg-transparent px-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {NEW_PAGE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
            Title
            <Input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && confirm()}
              placeholder="Page title"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
            Tags
            <Input
              value={tagsRaw}
              onChange={(e) => setTagsRaw(e.target.value)}
              placeholder="comma-separated"
            />
          </label>
          {path && (
            <div className="text-[11px] text-muted-foreground">
              path: <span className="font-mono">{path}</span>
            </div>
          )}
          {collision && (
            <div className="rounded border border-pending/40 bg-pending/10 px-2 py-1.5 text-[11.5px] text-pending">
              A page with this slug already exists.{" "}
              <button
                className="underline"
                onClick={() => {
                  onOpenExisting(collision.path)
                  onOpenChange(false)
                  reset()
                }}
              >
                Open {collision.title}
              </button>{" "}
              instead, or pick a different title.
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={!valid}>
            Create &amp; edit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
