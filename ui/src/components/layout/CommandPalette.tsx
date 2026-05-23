import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { FileText, FolderOpen, GitPullRequest, Sparkles } from "lucide-react"
import { api } from "@/lib/api"
import type { PageMeta, Source } from "@/types"
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

export function CommandPalette() {
  const navigate = useNavigate()
  const open = useAppStore((s) => s.cmdkOpen)
  const setOpen = useAppStore((s) => s.setCmdkOpen)
  const crs = useCrStore((s) => s.crs)
  const [query, setQuery] = useState("")
  const [pages, setPages] = useState<PageMeta[]>([])
  const [sources, setSources] = useState<Source[]>([])

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

  function go(to: string) {
    setOpen(false)
    setQuery("")
    navigate(to)
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search pages, sources, change requests…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>

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
