import { ListTodo } from "lucide-react"

export function JobsView() {
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[760px]">
        <h1 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold">
          <ListTodo className="size-5 text-primary" /> Background jobs
        </h1>
        <div className="rounded-lg border border-dashed py-12 text-center">
          <p className="text-[13px] text-muted-foreground">
            No background jobs running.
          </p>
          <p className="mx-auto mt-1 max-w-[420px] text-[12px] text-muted-foreground">
            Ingestion and lint currently run synchronously — progress is shown
            in the drawer at the bottom of the screen. Async job tracking is
            planned (SSE streaming).
          </p>
        </div>
      </div>
    </div>
  )
}
