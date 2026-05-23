import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import { TopBar } from "./TopBar"
import { Sidebar } from "./Sidebar"
import { CommandPalette } from "./CommandPalette"
import { ProgressDrawer } from "@/components/shared/ProgressDrawer"
import { OnboardingFlow } from "@/views/OnboardingFlow"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app"
import { useCrStore } from "@/stores/crs"

export function AppShell() {
  const setCmdkOpen = useAppStore((s) => s.setCmdkOpen)
  const needsOnboarding = useAppStore((s) => s.needsOnboarding)
  const setNeedsOnboarding = useAppStore((s) => s.setNeedsOnboarding)
  const fetchCrs = useCrStore((s) => s.fetch)
  const fetchBrains = useAppStore((s) => s.fetchBrains)

  // First-run check + CR fetch + brain sync at startup.
  useEffect(() => {
    api
      .getOnboarding()
      .then((o) => setNeedsOnboarding(o.needs_onboarding))
      .catch(() => setNeedsOnboarding(false))
    fetchCrs()
    fetchBrains()
  }, [fetchCrs, fetchBrains, setNeedsOnboarding])

  if (needsOnboarding) {
    return <OnboardingFlow onDone={() => setNeedsOnboarding(false)} />
  }

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