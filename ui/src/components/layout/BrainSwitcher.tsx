import { useState, useRef, useEffect } from "react"
import { ChevronDown, Check, Brain, Book, Code, Briefcase, FlaskConical, Lightbulb, Rocket, Folder } from "lucide-react"
import { useAppStore } from "@/stores/app"
import type { BrainIcon, RegisteredBrain } from "@/types"

const ICON_MAP: Record<BrainIcon, React.ReactNode> = {
  brain: <Brain className="size-4" />,
  book: <Book className="size-4" />,
  code: <Code className="size-4" />,
  briefcase: <Briefcase className="size-4" />,
  flask: <FlaskConical className="size-4" />,
  lightbulb: <Lightbulb className="size-4" />,
  rocket: <Rocket className="size-4" />,
  folder: <Folder className="size-4" />,
}

export function BrainSwitcher() {
  const [open, setOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const brainName = useAppStore((s) => s.brainName)
  const brains = useAppStore((s) => s.brains)
  const activeBrainId = useAppStore((s) => s.activeBrainId)
  const activateBrain = useAppStore((s) => s.activateBrain)
  const [switching, setSwitching] = useState(false)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const handleSelect = async (brain: RegisteredBrain) => {
    setOpen(false)
    if (brain.id === activeBrainId || switching) return
    setSwitching(true)
    try {
      // Switch on the backend (source of truth), then hard-reload so every
      // view refetches against the new active brain.
      await activateBrain(brain.id)
      window.location.reload()
    } catch {
      setSwitching(false)
    }
  }

  // Find active brain
  const activeBrain = brains.find((b) => b.id === activeBrainId)
  const displayName = activeBrain?.name || brainName || "no brain"
  const displayIcon = activeBrain?.icon ? ICON_MAP[activeBrain.icon] : null

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        className="ml-1 flex items-center gap-1.5 text-[13px] font-normal text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        {displayIcon && (
          <span className="text-muted-foreground">{displayIcon}</span>
        )}
        {displayName}
        <ChevronDown className="size-3" />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 min-w-[200px] rounded-md border bg-popover p-1 shadow-md">
          {brains.length === 0 ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              No brains registered.{" "}
              <a href="/settings" className="text-primary hover:underline">
                Add in Settings
              </a>
            </div>
          ) : (
            <ul className="space-y-0.5">
              {brains.map((brain) => {
                const missing = brain.valid === false
                return (
                  <li key={brain.id}>
                    <button
                      className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
                      onClick={() => handleSelect(brain)}
                      disabled={missing}
                      title={missing ? "Folder missing" : undefined}
                    >
                      <span className="text-muted-foreground">
                        {ICON_MAP[brain.icon ?? "brain"]}
                      </span>
                      <span className="flex-1 text-left">{brain.name}</span>
                      {missing && (
                        <span className="text-[10px] text-rejected">missing</span>
                      )}
                      {brain.id === activeBrainId && (
                        <Check className="size-3 text-primary" />
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}