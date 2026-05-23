export function Placeholder({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
      <h1 className="font-display text-lg font-semibold text-foreground">
        {title}
      </h1>
      {hint && <p className="text-[13px]">{hint}</p>}
    </div>
  )
}
