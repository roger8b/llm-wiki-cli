import { useEffect, useState } from "react"
import { useShallow } from "zustand/react/shallow"
import { Check, X, Pencil, Plus, FilePen, Trash2, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { timeAgo, pageTags, crKind } from "@/lib/format"
import {
  useCrStore,
  selectedCr,
  pendingCrs,
  settledCrs,
} from "@/stores/crs"
import type { ChangeRequest, FileChange } from "@/types"
import { DiffPanel } from "@/components/shared/DiffPanel"
import { diffValues } from "@/lib/diff"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"

function opIcon(op: FileChange["operation"]) {
  if (op === "delete") return <Trash2 className="size-3.5 text-rejected" />
  if (op === "update") return <FilePen className="size-3.5 text-pending" />
  return <Plus className="size-3.5 text-apply" />
}

// ─────────────────────────────────────────────── CR list (left pane)
function CrCard({ cr }: { cr: ChangeRequest }) {
  const selectedId = useCrStore((s) => s.selectedId)
  const select = useCrStore((s) => s.select)
  const selected = cr.id === selectedId
  const dot =
    cr.status === "applied"
      ? "bg-apply"
      : cr.status === "rejected"
        ? "bg-rejected"
        : "bg-pending"

  return (
    <button
      onClick={() => select(cr.id)}
      className={cn(
        "block w-full border-b border-l-[2.5px] border-l-transparent px-3.5 py-2.5 text-left transition-colors",
        "hover:bg-accent",
        selected && "border-l-primary bg-accent",
      )}
    >
      <div className="mb-1 flex items-center gap-1.5">
        <span className={cn("size-1.5 rounded-full", dot)} />
        <span className="font-mono text-[11px] font-semibold">{cr.id}</span>
      </div>
      <div className="mb-1 text-[12.5px] leading-snug">{cr.summary}</div>
      <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
        {cr.files_changed} files · {crKind(cr)} · {timeAgo(cr.created_at)}
        {pageTags(cr.changes).map((t) => (
          <span
            key={t}
            className="rounded border bg-secondary px-1.5 py-px text-[10px]"
          >
            {t}
          </span>
        ))}
      </div>
    </button>
  )
}

function CrList() {
  const pending = useCrStore(useShallow(pendingCrs))
  const settled = useCrStore(useShallow(settledCrs))
  return (
    <aside className="flex w-[280px] shrink-0 flex-col overflow-hidden border-r-[1.5px]">
      <div className="shrink-0 border-b-[1.5px] px-3.5 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Change Requests
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="bg-background px-3.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Pending ({pending.length})
        </div>
        {pending.map((cr) => (
          <CrCard key={cr.id} cr={cr} />
        ))}
        {pending.length === 0 && (
          <div className="px-3.5 py-3 text-[12px] text-muted-foreground">
            No pending change requests.
          </div>
        )}
        {settled.length > 0 && (
          <div className="bg-background px-3.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Resolved ({settled.length})
          </div>
        )}
        {settled.map((cr) => (
          <CrCard key={cr.id} cr={cr} />
        ))}
      </div>
    </aside>
  )
}

// ─────────────────────────────────────────────── CR detail (right pane)
function MonoBlock({ text }: { text: string }) {
  return (
    <div className="min-h-0 flex-1 overflow-hidden p-3">
      <div className="h-full overflow-auto rounded-md border bg-card p-4">
        <pre className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-foreground">
          {text || "(empty)"}
        </pre>
      </div>
    </div>
  )
}

function CrDetail({ cr }: { cr: ChangeRequest }) {
  const fileIdx = useCrStore((s) => s.selectedFileIdx)
  const selectFile = useCrStore((s) => s.selectFile)
  const tab = useCrStore((s) => s.tab)
  const setTab = useCrStore((s) => s.setTab)
  const apply = useCrStore((s) => s.apply)
  const reject = useCrStore((s) => s.reject)
  const busyId = useCrStore((s) => s.busyId)
  const editing = useCrStore((s) => s.editing)
  const setEditing = useCrStore((s) => s.setEditing)
  const updateFile = useCrStore((s) => s.updateFile)

  const change = cr.changes[fileIdx] ?? cr.changes[0]
  const isPending = cr.status === "pending_review"
  const busy = busyId === cr.id
  const disabled = !isPending || busy

  const [draft, setDraft] = useState("")
  const [saving, setSaving] = useState(false)

  // Per-file selection for partial apply (#184): all files checked by default,
  // reset whenever the selected CR changes.
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(cr.changes.map((c) => c.path)),
  )
  useEffect(() => {
    setSelected(new Set(cr.changes.map((c) => c.path)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cr.id])
  function toggleFile(path: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }
  const total = cr.changes.length
  const selectedCount = selected.size
  const partial = selectedCount > 0 && selectedCount < total
  const nothingSelected = isPending && selectedCount === 0

  // Seed the editor whenever edit mode is (re)entered — works for both the
  // Edit button and the ⌘E shortcut handled in the parent view.
  useEffect(() => {
    if (editing && change) setDraft(diffValues(change).newValue)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing])

  function startEditing() {
    if (!change) return
    setTab("after")
    setEditing(true)
  }

  async function handleSave() {
    if (!change) return
    setSaving(true)
    try {
      await updateFile(cr.id, change.path, draft)
      setEditing(false)
      setTab("diff")
      toast.success(`${change.path} updated`)
    } catch (e) {
      toast.error(`Edit failed: ${(e as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  async function handleApply() {
    // Full apply → omit paths; partial → send the checked subset (#184).
    const paths = partial ? [...selected] : undefined
    try {
      await apply(cr.id, paths)
      toast.success(
        paths ? `${cr.id}: ${paths.length} applied, rest rejected` : `${cr.id} applied`,
      )
    } catch (e) {
      toast.error(`Apply failed: ${(e as Error).message}`)
    }
  }
  async function handleReject() {
    try {
      await reject(cr.id)
      toast(`${cr.id} rejected`)
    } catch (e) {
      toast.error(`Reject failed: ${(e as Error).message}`)
    }
  }

  return (
    <section className="flex flex-1 flex-col overflow-hidden">
      {/* header */}
      <div className="flex shrink-0 items-center gap-2 border-b-[1.5px] bg-card px-5 py-3">
        <span className="font-mono text-[13px] font-bold">{cr.id}</span>
        <span className="rounded border bg-secondary px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {crKind(cr)}
        </span>
        {cr.edited_by_reviewer && (
          <span className="rounded border border-pending/40 bg-pending/10 px-1.5 py-0.5 text-[11px] text-pending">
            edited
          </span>
        )}
        <span className="ml-auto text-[11px] text-muted-foreground">
          {timeAgo(cr.created_at)}
        </span>
      </div>
      {/* summary */}
      <div className="shrink-0 border-b-[1.5px] bg-accent px-5 py-3 text-[13px] leading-relaxed">
        {cr.summary}
      </div>
      {/* tabs */}
      <div className="flex shrink-0 gap-0 border-b-[1.5px] bg-card px-5">
        {(["diff", "after", "before"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "border-b-2 border-transparent px-3.5 py-2 text-[12px] capitalize text-muted-foreground transition-colors hover:text-foreground",
              tab === t && "border-b-primary font-medium text-primary",
            )}
          >
            {t}
          </button>
        ))}
      </div>
      {/* body: files + content */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="flex w-[200px] shrink-0 flex-col overflow-hidden border-r-[1.5px]">
          <div className="shrink-0 border-b-[1.5px] bg-card px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Files ({cr.changes.length})
          </div>
          <div className="flex-1 overflow-y-auto">
            {cr.changes.map((c, i) => {
              const settledMark = !isPending
                ? cr.rejected_paths?.includes(c.path)
                  ? "rejected"
                  : cr.applied_paths?.includes(c.path)
                    ? "applied"
                    : null
                : null
              return (
                <div
                  key={c.path}
                  className={cn(
                    "flex w-full items-center gap-1.5 border-b px-3 py-[7px] transition-colors hover:bg-accent",
                    i === fileIdx && "bg-secondary",
                  )}
                >
                  {isPending && (
                    <Checkbox
                      checked={selected.has(c.path)}
                      onCheckedChange={() => toggleFile(c.path)}
                      aria-label={`Include ${c.path}`}
                      className="size-3.5 shrink-0"
                    />
                  )}
                  <button
                    onClick={() => selectFile(i)}
                    className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  >
                    {opIcon(c.operation)}
                    <span className="flex-1 truncate font-mono text-[11px]">
                      {c.path}
                    </span>
                  </button>
                  {settledMark === "applied" && (
                    <Check className="size-3.5 shrink-0 text-apply" />
                  )}
                  {settledMark === "rejected" && (
                    <X className="size-3.5 shrink-0 text-rejected" />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {change ? (
          editing && tab === "after" ? (
            <div className="flex min-h-0 flex-1 flex-col gap-2 p-3">
              <Textarea
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault()
                    setEditing(false)
                    setTab("diff")
                  }
                }}
                className="h-full flex-1 resize-none font-mono text-[12px] leading-relaxed"
                spellCheck={false}
              />
              <div className="flex shrink-0 items-center gap-2">
                <Button onClick={handleSave} disabled={saving} className="gap-1.5">
                  {saving ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Check className="size-4" />
                  )}
                  {saving ? "Saving…" : "Save"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditing(false)
                    setTab("diff")
                  }}
                  disabled={saving}
                >
                  Cancel
                  <kbd className="ml-1 font-mono text-[10px] opacity-65">Esc</kbd>
                </Button>
              </div>
            </div>
          ) : tab === "diff" ? (
            <DiffPanel change={change} />
          ) : (
            <MonoBlock
              text={
                tab === "after"
                  ? diffValues(change).newValue
                  : diffValues(change).oldValue
              }
            />
          )
        ) : (
          <div className="flex flex-1 items-center justify-center text-[13px] text-muted-foreground">
            No file changes.
          </div>
        )}
      </div>
      {/* actions */}
      <div className="flex shrink-0 items-center gap-2 border-t-[1.5px] bg-card px-5 py-3">
        <Button
          onClick={handleApply}
          disabled={disabled || nothingSelected}
          className="gap-1.5 bg-apply text-apply-foreground hover:bg-apply/90"
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Check className="size-4" />
          )}
          {busy
            ? "Applying…"
            : partial
              ? `Apply selected (${selectedCount})`
              : "Apply"}
          {!busy && !partial && (
            <kbd className="ml-0.5 font-mono text-[10px] opacity-65">⌘↵</kbd>
          )}
        </Button>
        {isPending && partial && (
          <span className="text-[11px] text-pending">
            the other {total - selectedCount} will be rejected
          </span>
        )}
        <Button
          onClick={handleReject}
          disabled={disabled}
          variant="destructive"
          className="gap-1.5"
        >
          <X className="size-4" /> Reject
          <kbd className="ml-0.5 font-mono text-[10px] opacity-65">⌘⌫</kbd>
        </Button>
        <Button
          variant="outline"
          disabled={disabled || editing || !change}
          onClick={startEditing}
          className="gap-1.5"
        >
          <Pencil className="size-4" /> Edit before apply
          <kbd className="ml-0.5 font-mono text-[10px] opacity-65">⌘E</kbd>
        </Button>
      </div>
    </section>
  )
}

// ─────────────────────────────────────────────── view
export function ReviewView() {
  const fetch = useCrStore((s) => s.fetch)
  const loading = useCrStore((s) => s.loading)
  const error = useCrStore((s) => s.error)
  const cr = useCrStore(selectedCr)
  const apply = useCrStore((s) => s.apply)
  const reject = useCrStore((s) => s.reject)

  useEffect(() => {
    fetch()
  }, [fetch])

  // keyboard shortcuts (apply / reject / edit the selected pending CR)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      const state = useCrStore.getState()
      const current = selectedCr(state)
      if (!current || current.status !== "pending_review" || state.busyId) return
      if (e.key.toLowerCase() === "e") {
        // ⌘E toggles edit mode on the "after" pane.
        e.preventDefault()
        if (!state.editing && current.changes.length > 0) {
          state.setTab("after")
          state.setEditing(true)
        }
        return
      }
      // Apply/reject must not fire while editing content.
      if (state.editing) return
      if (e.key === "Enter") {
        e.preventDefault()
        apply(current.id)
          .then(() => toast.success(`${current.id} applied`))
          .catch((err) => toast.error(`Apply failed: ${err.message}`))
      } else if (e.key === "Backspace") {
        e.preventDefault()
        reject(current.id)
          .then(() => toast(`${current.id} rejected`))
          .catch((err) => toast.error(`Reject failed: ${err.message}`))
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [apply, reject])

  return (
    <div className="flex flex-1 overflow-hidden">
      <CrList />
      {error ? (
        <div className="flex flex-1 items-center justify-center text-[13px] text-rejected">
          {error}
        </div>
      ) : cr ? (
        <CrDetail cr={cr} />
      ) : (
        <div className="flex flex-1 items-center justify-center text-[13px] text-muted-foreground">
          {loading ? "Loading…" : "Select a change request to review"}
        </div>
      )}
    </div>
  )
}
