import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronRight, FileText, Search, Trash2, Link2, Pencil } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { timeAgo } from "@/lib/format"
import type { PageDetail, PageMeta } from "@/types"
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

  // edit-page state (#186)
  const [editing, setEditing] = useState(false)
  const [savingEdit, setSavingEdit] = useState(false)

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
    if (!detail) return
    setSavingEdit(true)
    try {
      const { change_request_id } = await api.proposeEdit(detail.path, frontmatter, body)
      await refetchCrs()
      toast.success(`Proposed as ${change_request_id} — review to apply`)
      setEditing(false)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSavingEdit(false)
    }
  }

  const openPath = useCallback(async (path: string) => {
    setSelected(path)
    setBacklinks([])
    setEditing(false)
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
        <div className="shrink-0 border-b-[1.5px] p-2">
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

      {/* reader */}
      <section className="flex-1 overflow-y-auto">
        {detail ? (
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
                  onClick={() => setEditing(true)}
                  disabled={editing}
                >
                  <Pencil className="size-4" /> Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1.5 text-muted-foreground hover:text-destructive"
                  onClick={openDeleteDialog}
                  disabled={editing}
                >
                  <Trash2 className="size-4" /> Delete
                </Button>
              </div>
            </div>
            {editing ? (
              <div className="flex h-[calc(100vh-220px)] min-h-[400px] flex-col">
                <PageEditor
                  detail={detail}
                  titles={titles}
                  saving={savingEdit}
                  onSave={handleProposeEdit}
                  onCancel={() => setEditing(false)}
                />
              </div>
            ) : (
              <MarkdownReader content={detail.body} onWikiLink={onWikiLink} />
            )}

            {!editing && backlinks.length > 0 && (
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
    </div>
  )
}
