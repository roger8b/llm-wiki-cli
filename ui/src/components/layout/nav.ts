import {
  ClipboardCheck,
  FileText,
  FolderOpen,
  Sparkles,
  Network,
  ShieldCheck,
  ListTodo,
  Settings,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** "pending" pulls the live pending-CR count; "jobs" pulls active jobs. */
  badge?: "pending" | "jobs"
}

export const PRIMARY_NAV: NavItem[] = [
  { to: "/review", label: "Review", icon: ClipboardCheck, badge: "pending" },
  { to: "/wiki", label: "Wiki", icon: FileText },
  { to: "/sources", label: "Sources", icon: FolderOpen },
  { to: "/ask", label: "Ask", icon: Sparkles },
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/lint", label: "Lint", icon: ShieldCheck },
]

export const SECONDARY_NAV: NavItem[] = [
  { to: "/jobs", label: "Jobs", icon: ListTodo, badge: "jobs" },
  { to: "/settings", label: "Settings", icon: Settings },
]
