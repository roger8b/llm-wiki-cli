import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronRight, FileText, Search } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { timeAgo } from "@/lib/format"
import type { PageDetail, PageMeta } from "@/types"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import { Input } from "@/components/ui/input"

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

  // title → path map for wikilink resolution
  const titleMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const p of pages) m.set(p.title.toLowerCase(), p.path)
    return m
  }, [pages])

  const openPath = useCallback(async (path: string) => {
    setSelected(path)
    try {
      setDetail(await api.getPage(path))
    } catch (e) {
      toast.error((e as Error).message)
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
            <div className="mb-4 rounded-lg border bg-card px-4 py-2.5 text-[12px] text-muted-foreground">
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
            <MarkdownReader content={detail.body} onWikiLink={onWikiLink} />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
            Select a page
          </div>
        )}
      </section>
    </div>
  )
}
