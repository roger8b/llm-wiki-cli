import { cn } from "@/lib/utils"

/** A thin indeterminate progress bar for step-based (non-percentage) jobs. */
export function IndeterminateBar({ className }: { className?: string }) {
  return <div className={cn("bar-indeterminate h-1.5 w-full", className)} />
}
