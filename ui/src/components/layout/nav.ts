import {
  ClipboardCheck,
  FileText,
  FolderOpen,
  Sparkles,
  Network,
  ShieldCheck,
  ListTodo,
  BarChart3,
  Settings,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** "pending" pulls the live pending-CR count; "pending-source" pulls the
   *  pending-source count (#340); "jobs" pulls active jobs. */
  badge?: "pending" | "pending-source" | "jobs"
}

export const PRIMARY_NAV: NavItem[] = [
  { to: "/review", label: "Review", icon: ClipboardCheck, badge: "pending" },
  { to: "/wiki", label: "Wiki", icon: FileText },
  { to: "/sources", label: "Sources", icon: FolderOpen, badge: "pending-source" },
  { to: "/ask", label: "Ask", icon: Sparkles },
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/lint", label: "Lint", icon: ShieldCheck },
]

export const SECONDARY_NAV: NavItem[] = [
  { to: "/jobs", label: "Jobs", icon: ListTodo, badge: "jobs" },
  { to: "/observability", label: "Insights", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
]
