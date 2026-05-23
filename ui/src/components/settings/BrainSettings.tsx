import { useState } from "react"
import {
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Brain,
  FolderOpen,
  AlertTriangle,
  Book,
  Code,
  Briefcase,
  FlaskConical,
  Lightbulb,
  Rocket,
  Folder,
} from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app"
import type { BrainConfig, BrainIcon, RegisteredBrain } from "@/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const BRAIN_ICONS: { value: BrainIcon; icon: React.ReactNode; label: string }[] = [
  { value: "brain", icon: <Brain className="size-4" />, label: "Brain" },
  { value: "book", icon: <Book className="size-4" />, label: "Book" },
  { value: "code", icon: <Code className="size-4" />, label: "Code" },
  { value: "briefcase", icon: <Briefcase className="size-4" />, label: "Work" },
  { value: "flask", icon: <FlaskConical className="size-4" />, label: "Research" },
  { value: "lightbulb", icon: <Lightbulb className="size-4" />, label: "Ideas" },
  { value: "rocket", icon: <Rocket className="size-4" />, label: "Project" },
  { value: "folder", icon: <Folder className="size-4" />, label: "Folder" },
]

function getIconComponent(icon: BrainIcon) {
  return BRAIN_ICONS.find((i) => i.value === icon)?.icon ?? <Brain className="size-4" />
}

interface BrainFormProps {
  initial?: Partial<BrainConfig>
  onSubmit: (data: BrainConfig) => void
  onCancel: () => void
  submitLabel?: string
  loading?: boolean
}

function BrainForm({ initial, onSubmit, onCancel, submitLabel = "Add", loading }: BrainFormProps) {
  const [name, setName] = useState(initial?.name ?? "")
  const [path, setPath] = useState(initial?.path ?? "")
  const [icon, setIcon] = useState<BrainIcon>(initial?.icon ?? "brain")

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      toast.error("Brain name is required")
      return
    }
    if (!path.trim()) {
      toast.error("Brain path is required")
      return
    }
    onSubmit({ name: name.trim(), path: path.trim(), icon })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-md border bg-muted/30 p-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-[11px]">Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-wiki"
            className="h-8 text-[13px]"
            autoFocus
            disabled={loading}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-[11px]">Path</Label>
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/Users/name/wiki/my-wiki"
            className="h-8 text-[13px] font-mono"
            disabled={loading}
          />
        </div>
      </div>

      {/* Icon selector */}
      <div className="space-y-1.5">
        <Label className="text-[11px]">Icon</Label>
        <div className="flex flex-wrap gap-1.5">
          {BRAIN_ICONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setIcon(opt.value)}
              className={cn(
                "flex size-8 items-center justify-center rounded-md border transition-colors",
                icon === opt.value
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-transparent bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
              title={opt.label}
            >
              {opt.icon}
            </button>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={loading}>
          <X className="mr-1 size-3.5" /> Cancel
        </Button>
        <Button type="submit" size="sm" disabled={loading}>
          {loading ? (
            <span className="mr-1 size-3.5 animate-spin rounded-full border border-current border-t-transparent" />
          ) : (
            <Check className="mr-1 size-3.5" />
          )}
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

interface BrainItemProps {
  brain: RegisteredBrain
  isActive: boolean
  onActivate: () => void
  onEdit: () => void
  onDelete: () => void
}

function BrainItem({ brain, isActive, onActivate, onEdit, onDelete }: BrainItemProps) {
  const iconComponent = getIconComponent(brain.icon ?? "brain")

  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-md border px-3 py-2.5 transition-colors",
        isActive ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/50",
      )}
    >
      <button
        onClick={onActivate}
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-full border-2 text-[10px] font-bold transition-colors",
          isActive
            ? "border-primary bg-primary text-primary-foreground"
            : "border-muted-foreground/30 text-transparent hover:border-muted-foreground/50",
        )}
      >
        {isActive && "✓"}
      </button>

      {/* Icon */}
      <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted/50 text-muted-foreground">
        {iconComponent}
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">{brain.name}</div>
        <div className="truncate font-mono text-[11px] text-muted-foreground">{brain.path}</div>
      </div>
      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <Button variant="ghost" size="icon" className="size-7" onClick={onEdit}>
          <Pencil className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-rejected hover:text-rejected"
          onClick={onDelete}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}

export function BrainSettings() {
  const brains = useAppStore((s) => s.brains)
  const activeBrainId = useAppStore((s) => s.activeBrainId)
  const addBrain = useAppStore((s) => s.addBrain)
  const updateBrain = useAppStore((s) => s.updateBrain)
  const removeBrain = useAppStore((s) => s.removeBrain)
  const setActiveBrainId = useAppStore((s) => s.setActiveBrainId)
  const setBrainName = useAppStore((s) => s.setBrainName)

  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const activeBrain = brains.find((b) => b.id === activeBrainId)

  function handleAdd(data: BrainConfig) {
    const id = crypto.randomUUID()
    const brain: RegisteredBrain = {
      id,
      name: data.name,
      path: data.path,
      icon: data.icon ?? "brain",
      createdAt: new Date().toISOString(),
    }
    addBrain(brain)
    if (brains.length === 0) {
      setActiveBrainId(id)
      setBrainName(data.name)
    }
    setAdding(false)
    toast.success(`Brain "${data.name}" added`)
  }

  function handleEdit(id: string, data: BrainConfig) {
    setLoading(true)
    setTimeout(() => {
      updateBrain(id, data)
      setEditingId(null)
      setLoading(false)
      toast.success(`Brain "${data.name}" updated`)
    }, 150)
  }

  function handleDelete(id: string) {
    setDeletingId(id)
  }

  function confirmDelete() {
    if (!deletingId) return
    const brain = brains.find((b) => b.id === deletingId)
    removeBrain(deletingId)
    setDeletingId(null)
    toast.info(`Brain "${brain?.name}" removed`)
  }

  function cancelDelete() {
    setDeletingId(null)
  }

  function handleActivate(brain: RegisteredBrain) {
    setActiveBrainId(brain.id)
    setBrainName(brain.name)
    toast.success(`Switched to brain "${brain.name}"`)
  }

  return (
    <div className="mt-4 rounded-lg border bg-card p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="size-4 text-muted-foreground" />
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Brains
          </span>
          {activeBrain && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
              {activeBrain.name}
            </span>
          )}
        </div>
        {!adding && (
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 h-7 text-[11px]"
            onClick={() => setAdding(true)}
          >
            <Plus className="size-3" /> Add
          </Button>
        )}
      </div>

      {/* Form when adding */}
      {adding && (
        <BrainForm
          onSubmit={handleAdd}
          onCancel={() => setAdding(false)}
          submitLabel="Add"
        />
      )}

      {/* Delete confirmation */}
      {deletingId && (
        <div className="mb-3 flex items-center gap-3 rounded-md border border-rejected/30 bg-rejected/10 px-4 py-3">
          <AlertTriangle className="size-4 shrink-0 text-rejected" />
          <div className="flex-1 text-[13px]">
            Delete <strong>{brains.find((b) => b.id === deletingId)?.name}</strong>? This cannot be undone.
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={cancelDelete}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={confirmDelete}>
              Delete
            </Button>
          </div>
        </div>
      )}

      {/* List or empty state */}
      {brains.length === 0 && !adding ? (
        <div className="rounded-md border border-dashed py-8 text-center">
          <Brain className="mx-auto mb-2 size-6 text-muted-foreground/50" />
          <p className="text-[12px] text-muted-foreground">No brains registered yet.</p>
          <p className="text-[11px] text-muted-foreground/70 mt-1">
            Click "Add" above to register your first brain.
          </p>
        </div>
      ) : brains.length > 0 ? (
        <div className="max-h-64 space-y-2 pr-1 overflow-y-auto">
          {brains.map((brain) =>
            editingId === brain.id ? (
              <BrainForm
                key={brain.id}
                initial={brain}
                onSubmit={(data) => handleEdit(brain.id, data)}
                onCancel={() => setEditingId(null)}
                submitLabel="Save"
                loading={loading}
              />
            ) : (
              <BrainItem
                key={brain.id}
                brain={brain}
                isActive={brain.id === activeBrainId}
                onActivate={() => handleActivate(brain)}
                onEdit={() => setEditingId(brain.id)}
                onDelete={() => handleDelete(brain.id)}
              />
            ),
          )}
        </div>
      ) : null}

      {/* Footer hint */}
      {brains.length > 0 && (
        <p className="mt-3 text-[11px] text-muted-foreground">
          <FolderOpen className="mr-1 inline size-3" />
          Persisted in browser storage.
        </p>
      )}
    </div>
  )
}