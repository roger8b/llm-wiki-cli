import { useMemo, useRef, useState } from "react"
import { Check, Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { MarkdownReader } from "@/components/shared/MarkdownReader"
import type { PageDetail, PageType } from "@/types"

const PAGE_TYPES: PageType[] = [
  "concept",
  "entity",
  "source_summary",
  "synthesis",
  "decision",
  "project",
  "research",
]
const CONFIDENCES = ["low", "medium", "high"] as const

export interface PageEditorProps {
  detail: PageDetail
  /** Existing page titles, for `[[` wikilink autocomplete. */
  titles: string[]
  onSave: (frontmatter: Record<string, unknown>, body: string) => Promise<void>
  onCancel: () => void
  saving?: boolean
}

export function asTags(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String)
  if (typeof v === "string" && v.trim()) return v.split(/[,\s]+/).filter(Boolean)
  return []
}

/** Manual page editor proposed as a CR (#186); reused by "New page" (#187). */
export function PageEditor({ detail, titles, onSave, onCancel, saving }: PageEditorProps) {
  const fm = detail.frontmatter
  const [title, setTitle] = useState(String(fm.title ?? ""))
  const [type, setType] = useState<PageType>(
    (PAGE_TYPES.includes(fm.type as PageType) ? fm.type : "concept") as PageType,
  )
  const [confidence, setConfidence] = useState(String(fm.confidence ?? "medium"))
  const [tags, setTags] = useState<string[]>(asTags(fm.tags))
  const [tagDraft, setTagDraft] = useState("")
  const [body, setBody] = useState(detail.body)

  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const [acOpen, setAcOpen] = useState(false)
  const [acQuery, setAcQuery] = useState("")

  const valid = title.trim().length > 0 && PAGE_TYPES.includes(type)

  const suggestions = useMemo(() => {
    if (!acOpen) return []
    const q = acQuery.toLowerCase()
    return titles.filter((t) => t.toLowerCase().includes(q)).slice(0, 8)
  }, [acOpen, acQuery, titles])

  function addTag(raw: string) {
    const t = raw.trim().replace(/,$/, "")
    if (t && !tags.includes(t)) setTags([...tags, t])
    setTagDraft("")
  }

  // Detect an open `[[` token immediately before the caret and drive the popover.
  function onBodyChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    setBody(value)
    const caret = e.target.selectionStart ?? value.length
    const upto = value.slice(0, caret)
    const open = upto.lastIndexOf("[[")
    if (open >= 0 && !upto.slice(open).includes("]]")) {
      setAcOpen(true)
      setAcQuery(upto.slice(open + 2))
    } else {
      setAcOpen(false)
    }
  }

  function insertWikilink(name: string) {
    const el = bodyRef.current
    if (!el) return
    const caret = el.selectionStart ?? body.length
    const before = body.slice(0, caret)
    const open = before.lastIndexOf("[[")
    const next = before.slice(0, open) + `[[${name}]]` + body.slice(caret)
    setBody(next)
    setAcOpen(false)
    // restore focus after React commits
    requestAnimationFrame(() => {
      el.focus()
      const pos = open + name.length + 4
      el.setSelectionRange(pos, pos)
    })
  }

  function handleSave() {
    const frontmatter: Record<string, unknown> = {
      ...fm,
      title: title.trim(),
      type,
      tags,
      confidence,
    }
    void onSave(frontmatter, body)
  }

  const selectCls =
    "h-9 rounded-md border bg-transparent px-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-ring"

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {/* frontmatter form */}
      <div className="grid grid-cols-2 gap-3">
        <label className="col-span-2 flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
          Title
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Page title"
            aria-label="Title"
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
          Type
          <select
            value={type}
            onChange={(e) => setType(e.target.value as PageType)}
            className={selectCls}
            aria-label="Type"
          >
            {PAGE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
          Confidence
          <select
            value={confidence}
            onChange={(e) => setConfidence(e.target.value)}
            className={selectCls}
            aria-label="Confidence"
          >
            {CONFIDENCES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <div className="col-span-2 flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
          Tags
          <div className="flex flex-wrap items-center gap-1 rounded-md border px-2 py-1.5">
            {tags.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-[11px] text-foreground"
              >
                {t}
                <button onClick={() => setTags(tags.filter((x) => x !== t))} aria-label={`Remove ${t}`}>
                  <X className="size-3" />
                </button>
              </span>
            ))}
            <input
              value={tagDraft}
              onChange={(e) => setTagDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault()
                  addTag(tagDraft)
                } else if (e.key === "Backspace" && !tagDraft && tags.length) {
                  setTags(tags.slice(0, -1))
                }
              }}
              onBlur={() => tagDraft && addTag(tagDraft)}
              placeholder="add tag…"
              className="min-w-[80px] flex-1 bg-transparent text-[12px] outline-none"
              aria-label="Add tag"
            />
          </div>
        </div>
        {/* read-only provenance */}
        <div className="col-span-2 flex flex-wrap gap-x-4 text-[11px] text-muted-foreground">
          {fm.updated_at ? <span>updated_at: {String(fm.updated_at)} (auto)</span> : null}
          {Array.isArray(fm.sources) && fm.sources.length > 0 ? (
            <span>sources: {(fm.sources as string[]).join(", ")}</span>
          ) : null}
        </div>
      </div>

      {/* body editor + live preview */}
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
        <div className="relative flex min-h-0 flex-col">
          <textarea
            ref={bodyRef}
            value={body}
            onChange={onBodyChange}
            onKeyDown={(e) => {
              if (acOpen && suggestions.length && e.key === "Enter") {
                e.preventDefault()
                insertWikilink(suggestions[0])
              } else if (e.key === "Escape") {
                if (acOpen) setAcOpen(false)
                else onCancel()
              }
            }}
            spellCheck={false}
            className="h-full flex-1 resize-none rounded-md border p-3 font-mono text-[12px] leading-relaxed focus:outline-none focus:ring-1 focus:ring-ring"
            aria-label="Body"
          />
          {acOpen && suggestions.length > 0 && (
            <ul className="absolute bottom-2 left-2 z-10 max-h-48 w-64 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
              {suggestions.map((s) => (
                <li key={s}>
                  <button
                    onClick={() => insertWikilink(s)}
                    className="flex w-full items-center rounded px-2 py-1 text-left text-[12px] hover:bg-accent"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="min-h-0 overflow-y-auto rounded-md border p-3">
          <MarkdownReader content={body} />
        </div>
      </div>

      {/* actions */}
      <div className="flex shrink-0 items-center gap-2">
        <Button onClick={handleSave} disabled={!valid || saving} className="gap-1.5">
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
          {saving ? "Saving…" : "Propose edit"}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
          <kbd className="ml-1 font-mono text-[10px] opacity-65">Esc</kbd>
        </Button>
        {!valid && (
          <span className="text-[11px] text-rejected">title and a valid type are required</span>
        )}
      </div>
    </div>
  )
}
