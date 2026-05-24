import { lazy, Suspense } from "react"
import { createBrowserRouter, Navigate } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
const ReviewView = lazy(() =>
  import("@/views/ReviewView").then((m) => ({ default: m.ReviewView })),
)

// Lazy-load ALL views to keep the initial main chunk small.
// Even lightweight views like Sources are deferred to avoid pulling in their
// dependencies (cmdk, react-markdown, diff libs, zustand stores) upfront.
const SourcesView = lazy(() =>
  import("@/views/SourcesView").then((m) => ({ default: m.SourcesView })),
)
const AskView = lazy(() =>
  import("@/views/AskView").then((m) => ({ default: m.AskView })),
)
const WikiView = lazy(() =>
  import("@/views/WikiView").then((m) => ({ default: m.WikiView })),
)
const LintView = lazy(() =>
  import("@/views/LintView").then((m) => ({ default: m.LintView })),
)
const JobsView = lazy(() =>
  import("@/views/JobsView").then((m) => ({ default: m.JobsView })),
)
const SettingsView = lazy(() =>
  import("@/views/SettingsView").then((m) => ({ default: m.SettingsView })),
)
const GraphView = lazy(() =>
  import("@/views/GraphView").then((m) => ({ default: m.GraphView })),
)

function Lazy({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center text-[13px] text-muted-foreground">
          Loading…
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/review" replace /> },
      { path: "review", element: <Lazy><ReviewView /></Lazy> },
      { path: "wiki", element: <Lazy><WikiView /></Lazy> },
      { path: "sources", element: <Lazy><SourcesView /></Lazy> },
      { path: "ask", element: <Lazy><AskView /></Lazy> },
      { path: "graph", element: <Lazy><GraphView /></Lazy> },
      { path: "lint", element: <Lazy><LintView /></Lazy> },
      { path: "jobs", element: <Lazy><JobsView /></Lazy> },
      { path: "settings", element: <Lazy><SettingsView /></Lazy> },
    ],
  },
])
