import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import { TopBar } from "./TopBar"
import { Sidebar } from "./Sidebar"
import { CommandPalette } from "./CommandPalette"
import { ProgressDrawer } from "@/components/shared/ProgressDrawer"
import { useAppStore } from "@/stores/app"
import { useCrStore } from "@/stores/crs"

export function AppShell() {
  const setCmdkOpen = useAppStore((s) => s.setCmdkOpen)
  const fetchCrs = useCrStore((s) => s.fetch)

  // Fetch CRs once at startup so the pending badge is correct on any screen.
  useEffect(() => {
    fetchCrs()
  }, [fetchCrs])

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TopBar onOpenSearch={() => setCmdkOpen(true)} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
      <ProgressDrawer />
      <CommandPalette />
    </div>
  )
}
