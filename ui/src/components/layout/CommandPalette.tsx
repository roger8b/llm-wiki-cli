import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { FileText, FolderOpen, GitPullRequest, Sparkles, Search } from "lucide-react"
import { api } from "@/lib/api"
import type { PageMeta, SearchResult, Source } from "@/types"
import { useAppStore } from "@/stores/app"
import { useCrStore } from "@/stores/crs"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"

/** Render an FTS snippet, turning the «…» highlight markers into <mark>. */
export function renderSnippet(snippet: string): React.ReactNode[] {
  return snippet.split(/[«»]/).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded bg-primary/20 px-0.5 text-foreground">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}

export function CommandPalette() {
  const navigate = useNavigate()
  const open = useAppStore((s) => s.cmdkOpen)
  const setOpen = useAppStore((s) => s.setCmdkOpen)
  const crs = useCrStore((s) => s.crs)
  const [query, setQuery] = useState("")
  const [pages, setPages] = useState<PageMeta[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const typeByPath = useMemo(() => {
    const m = new Map<string, string>()
    for (const p of pages) m.set(p.path, p.type)
    return m
  }, [pages])

  // global ⌘K / Ctrl+K
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen(!useAppStore.getState().cmdkOpen)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [setOpen])

  // lazy-load the index when first opened
  useEffect(() => {
    if (!open || pages.length > 0) return
    api.listPages().then(setPages).catch(() => {})
    api.listSources().then(setSources).catch(() => {})
  }, [open, pages.length])

  // Debounced content search (#188): ≥3 chars, 250ms, cancel the prior request.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 3) {
      setResults([])
      setSearching(false)
      abortRef.current?.abort()
      return
    }
    const timer = setTimeout(() => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setSearching(true)
      api
        .search(q, 8, ctrl.signal)
        .then((r) => {
          setResults(r)
          setSearching(false)
        })
        .catch(() => {
          // aborted or backend off — stay silent in the palette
          if (!ctrl.signal.aborted) setSearching(false)
        })
    }, 250)
    return () => clearTimeout(timer)
  }, [query])

  function go(to: string) {
    abortRef.current?.abort()
    setOpen(false)
    setQuery("")
    setResults([])
    navigate(to)
  }

  // Group search results by page type, preserving server score order.
  const resultGroups = useMemo(() => {
    const groups = new Map<string, SearchResult[]>()
    for (const r of results) {
      const t = typeByPath.get(r.path) ?? "other"
      ;(groups.get(t) ?? groups.set(t, []).get(t)!).push(r)
    }
    return [...groups.entries()]
  }, [results, typeByPath])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search pages, sources, change requests…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>

        <CommandGroup heading="Actions">
          <CommandItem
            value="New wiki page create"
            onSelect={() => go("/wiki?new=1")}
          >
            New wiki page
          </CommandItem>
          <CommandItem
            value="Capture URL web article source ingest"
            onSelect={() => go("/sources?add=url")}
          >
            Capture URL…
          </CommandItem>
        </CommandGroup>

        {pages.length > 0 && (
          <CommandGroup heading="Pages">
            {pages.map((p) => (
              <CommandItem
                key={p.path}
                value={`${p.title} ${p.path}`}
                onSelect={() => go(`/wiki?q=${encodeURIComponent(p.title)}`)}
              >
                <FileText className="size-4 text-muted-foreground" />
                <span>{p.title}</span>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                  {p.path}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {sources.length > 0 && (
          <CommandGroup heading="Sources">
            {sources.map((s) => (
              <CommandItem
                key={s.path}
                value={`${s.title ?? ""} ${s.path}`}
                onSelect={() => go("/sources")}
              >
                <FolderOpen className="size-4 text-muted-foreground" />
                <span>{s.title ?? s.path.split("/").pop()}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {crs.length > 0 && (
          <CommandGroup heading="Change requests">
            {crs.map((c) => (
              <CommandItem
                key={c.id}
                value={`${c.id} ${c.summary ?? ""}`}
                onSelect={() => go("/review")}
              >
                <GitPullRequest className="size-4 text-muted-foreground" />
                <span className="font-mono text-[12px]">{c.id}</span>
                <span className="ml-auto truncate text-[11px] text-muted-foreground">
                  {c.summary}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {query.trim().length >= 3 && (searching || results.length > 0) && (
          <>
            {searching && results.length === 0 && (
              <CommandGroup heading="Search wiki" forceMount>
                <CommandItem value={`__searching ${query}`} forceMount disabled>
                  <Search className="size-4 animate-pulse text-muted-foreground" />
                  Searching…
                </CommandItem>
              </CommandGroup>
            )}
            {resultGroups.map(([type, items]) => (
              <CommandGroup key={type} heading={`Search · ${type}`} forceMount>
                {items.map((r) => (
                  <CommandItem
                    key={r.path}
                    // include the query so cmdk's filter keeps the server hits
                    value={`${query} ${r.title} ${r.path}`}
                    forceMount
                    onSelect={() => go(`/wiki?path=${encodeURIComponent(r.path)}`)}
                  >
                    <Search className="size-4 shrink-0 text-muted-foreground" />
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate">{r.title}</span>
                      {r.snippet && (
                        <span className="truncate text-[11px] text-muted-foreground">
                          {renderSnippet(r.snippet)}
                        </span>
                      )}
                    </div>
                    {r.source === "semantic" && (
                      <span className="ml-auto shrink-0 text-[10px] text-primary">
                        semantic
                      </span>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </>
        )}

        {query.trim() && (
          <CommandGroup heading="Ask" forceMount>
            <CommandItem
              value={query}
              forceMount
              onSelect={() => go(`/ask?q=${encodeURIComponent(query)}`)}
            >
              <Sparkles className="size-4 text-primary" />
              Ask the wiki: “{query}” →
            </CommandItem>
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  )
}
