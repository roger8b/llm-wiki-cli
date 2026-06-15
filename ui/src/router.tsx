import { lazy, Suspense, type ComponentType } from "react"
import {
  createBrowserRouter,
  Navigate,
  useRouteError,
} from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { ReviewView } from "@/views/ReviewView"

// ReviewView is the default landing screen, so it loads EAGERLY (part of the
// main chunk). Lazy-loading it meant the very first paint triggered a dynamic
// import(); on a cold first launch the backend is still warming up and that
// chunk fetch could fail with "Importing a module script failed" (it worked on
// the second launch once the WebView had cached the chunk).
//
// The remaining views are code-split via lazyWithRetry: if a chunk fetch fails
// transiently (cold backend, dropped keep-alive), retry once before surfacing
// the error.
function lazyWithRetry<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      return await factory()
    } catch {
      await new Promise((r) => setTimeout(r, 400))
      return await factory()
    }
  })
}

const SourcesView = lazyWithRetry(() =>
  import("@/views/SourcesView").then((m) => ({ default: m.SourcesView })),
)
const AskView = lazyWithRetry(() =>
  import("@/views/AskView").then((m) => ({ default: m.AskView })),
)
const WikiView = lazyWithRetry(() =>
  import("@/views/WikiView").then((m) => ({ default: m.WikiView })),
)
const LintView = lazyWithRetry(() =>
  import("@/views/LintView").then((m) => ({ default: m.LintView })),
)
const JobsView = lazyWithRetry(() =>
  import("@/views/JobsView").then((m) => ({ default: m.JobsView })),
)
const SettingsView = lazyWithRetry(() =>
  import("@/views/SettingsView").then((m) => ({ default: m.SettingsView })),
)
const GraphView = lazyWithRetry(() =>
  import("@/views/GraphView").then((m) => ({ default: m.GraphView })),
)
const InsightsView = lazyWithRetry(() =>
  import("@/views/InsightsView").then((m) => ({ default: m.InsightsView })),
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

/** Route-level error screen — surfaces the real error (the WebView has no
 *  devtools in release) and offers a reload. */
function RouteError() {
  const error = useRouteError() as Error & { statusText?: string }
  const message =
    error?.statusText || error?.message || "Unknown error"
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <div>
        <h1 className="font-display text-lg font-semibold">Something went wrong</h1>
        <p className="mt-1 max-w-[600px] text-[13px] text-muted-foreground">
          {message}
        </p>
      </div>
      {error?.stack && (
        <pre className="max-h-48 max-w-[640px] overflow-auto rounded-md border bg-muted/40 p-3 text-left text-[11px] text-muted-foreground">
          {error.stack}
        </pre>
      )}
      <button
        onClick={() => window.location.reload()}
        className="rounded-md bg-primary px-4 py-1.5 text-[13px] font-medium text-primary-foreground hover:bg-primary/90"
      >
        Reload
      </button>
    </div>
  )
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Navigate to="/review" replace /> },
      { path: "review", element: <ReviewView /> },
      { path: "wiki", element: <Lazy><WikiView /></Lazy> },
      { path: "sources", element: <Lazy><SourcesView /></Lazy> },
      { path: "ask", element: <Lazy><AskView /></Lazy> },
      { path: "graph", element: <Lazy><GraphView /></Lazy> },
      { path: "lint", element: <Lazy><LintView /></Lazy> },
      { path: "jobs", element: <Lazy><JobsView /></Lazy> },
      { path: "observability", element: <Lazy><InsightsView /></Lazy> },
      { path: "settings", element: <Lazy><SettingsView /></Lazy> },
    ],
  },
])
