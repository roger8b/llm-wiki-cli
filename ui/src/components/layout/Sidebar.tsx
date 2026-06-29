import { NavLink } from "react-router-dom"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app"
import { PRIMARY_NAV, SECONDARY_NAV, type NavItem } from "./nav"

function NavRow({ item }: { item: NavItem }) {
  const pendingCount = useAppStore((s) => s.pendingCount)
  const pendingSourceCount = useAppStore((s) => s.pendingSourceCount)
  const activeJobs = useAppStore((s) => s.activeJobs)

  // Each badge kind maps to its own counter. Splitting "pending" (Review's CR
  // count) and "pending-source" (Sources' source count) lets two nav items
  // each carry their own live badge without sharing state (#340).
  const count =
    item.badge === "pending"
      ? pendingCount
      : item.badge === "pending-source"
        ? pendingSourceCount
        : item.badge === "jobs"
          ? activeJobs
          : undefined
  const isPendingBadge = item.badge === "pending" || item.badge === "pending-source"

  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-2 px-3.5 py-[7px] text-[13px] no-underline transition-colors",
          "border-l-[2.5px] border-transparent text-muted-foreground",
          "hover:bg-accent hover:text-foreground",
          isActive &&
            "border-l-primary bg-accent font-medium text-foreground",
        )
      }
    >
      <item.icon className="size-4 shrink-0" strokeWidth={2} />
      <span className="flex-1">{item.label}</span>
      {isPendingBadge && count !== undefined && count > 0 && (
        <span className="rounded-[10px] bg-pending px-1.5 py-px font-mono text-[10px] font-semibold text-white">
          {count}
        </span>
      )}
      {item.badge === "jobs" && (
        <span className="font-mono text-[10px] text-muted-foreground">
          {count ?? 0}
        </span>
      )}
    </NavLink>
  )
}

export function Sidebar() {
  return (
    <nav className="flex w-[var(--sidebar-w)] shrink-0 flex-col overflow-hidden border-r-[1.5px] bg-card max-[900px]:w-14">
      <div className="border-b-[1.5px] py-2.5">
        {PRIMARY_NAV.map((item) => (
          <NavRow key={item.to} item={item} />
        ))}
      </div>
      <div className="py-2.5">
        {SECONDARY_NAV.map((item) => (
          <NavRow key={item.to} item={item} />
        ))}
      </div>
    </nav>
  )
}
