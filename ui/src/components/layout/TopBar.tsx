import { useNavigate } from "react-router-dom"
import { ChevronDown, Search, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAppStore } from "@/stores/app"
import { BrainSwitcher } from "./BrainSwitcher"

interface TopBarProps {
  onOpenSearch?: () => void
}

export function TopBar({ onOpenSearch }: TopBarProps) {
  const navigate = useNavigate()
  const pendingCount = useAppStore((s) => s.pendingCount)
  const brains = useAppStore((s) => s.brains)

  // Show brain switcher only if brains are registered
  const showBrainSwitcher = brains.length > 0

  return (
    <header className="flex h-[var(--topbar-h)] shrink-0 items-center gap-3 border-b-[1.5px] bg-card px-4">
      {/* Brand + brain switcher */}
      <div className="flex items-center gap-1.5 font-display text-[15px] font-semibold">
        <span className="flex size-5 items-center justify-center rounded-[5px] bg-primary text-[11px] text-primary-foreground">
          ◈
        </span>
        llm-wiki
        {showBrainSwitcher ? (
          <BrainSwitcher />
        ) : (
          <button
            className="ml-1 flex items-center gap-1 text-[13px] font-normal text-muted-foreground hover:text-foreground"
            onClick={() => navigate("/settings")}
            title="Add brains in Settings"
          >
            no brain
            <ChevronDown className="size-3" />
          </button>
        )}
      </div>

      {/* Right actions */}
      <div className="ml-auto flex items-center gap-2.5">
        <div className="flex items-center gap-1.5 rounded-full border-[1.5px] bg-secondary px-2.5 py-[3px] text-xs text-muted-foreground">
          <span className="size-[7px] rounded-full bg-pending" />
          <strong className="text-foreground">{pendingCount}</strong> pending
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-[30px] text-muted-foreground"
          title="Search (⌘K)"
          onClick={onOpenSearch}
        >
          <Search className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-[30px] text-muted-foreground"
          title="Settings"
          onClick={() => navigate("/settings")}
        >
          <Settings className="size-4" />
        </Button>
      </div>
    </header>
  )
}
