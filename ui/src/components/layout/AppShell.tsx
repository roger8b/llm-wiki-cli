import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import { TopBar } from "./TopBar"
import { Sidebar } from "./Sidebar"
import { CommandPalette } from "./CommandPalette"
import { ProgressDrawer } from "@/components/shared/ProgressDrawer"
import { ProgressReopener } from "@/components/shared/ProgressReopener"
import { OnboardingFlow } from "@/views/OnboardingFlow"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app"
import { useCrStore } from "@/stores/crs"
import { useJobStore } from "@/stores/jobs"

export function AppShell() {
  const setCmdkOpen = useAppStore((s) => s.setCmdkOpen)
  const needsOnboarding = useAppStore((s) => s.needsOnboarding)
  const setNeedsOnboarding = useAppStore((s) => s.setNeedsOnboarding)
  const fetchCrs = useCrStore((s) => s.fetch)
  const fetchBrains = useAppStore((s) => s.fetchBrains)
  const fetchJobs = useJobStore((s) => s.fetch)

  // First-run check + CR fetch + brain sync + job polling at startup.
  useEffect(() => {
    api
      .getOnboarding()
      .then((o) => setNeedsOnboarding(o.needs_onboarding))
      .catch((err) => {
        // A failed onboarding probe (offline, auth race, transient 500) must
        // NOT silently land the user on an empty Review screen — that was the
        // bug on fresh installs. Assume the safer fresh-install path and show
        // onboarding; a returning user can step through it again if needed.
        console.error("getOnboarding failed; defaulting to onboarding:", err)
        setNeedsOnboarding(true)
      })
    fetchCrs()
    fetchBrains()
    fetchJobs()
    const timer = setInterval(() => {
      fetchJobs()
    }, 4000)

    return () => clearInterval(timer)
  }, [fetchCrs, fetchBrains, setNeedsOnboarding, fetchJobs])

  // While the first-run probe is in flight, render a loading splash instead of
  // flashing the empty review screen.
  if (needsOnboarding === null) {
    return (
      <div className="flex h-screen items-center justify-center text-[13px] text-muted-foreground">
        Loading…
      </div>
    )
  }
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
      <ProgressReopener />
      <CommandPalette />
    </div>
  )
}