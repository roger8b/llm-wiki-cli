import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { FileText, Archive, Quote, AlertTriangle } from "lucide-react"
import type { Citation } from "@/types"
import { cn } from "@/lib/utils"

// Turn a brain path into a friendlier label (filename without extension).
function labelFor(path: string): string {
  const base = path.split("/").pop() ?? path
  return base.replace(/\.md$/, "")
}

interface CitationCardProps {
  index: number
  citation: Citation
  pageTitles?: Record<string, string>
}

function CitationCard({ index, citation, pageTitles }: CitationCardProps) {
  const navigate = useNavigate()
  const [showQuote, setShowQuote] = useState(false)

  const isSource = !citation.page && Boolean(citation.source)
  const ref = citation.page ?? citation.source ?? "?"
  const invalid = Boolean(citation.invalid)
  const title = (citation.page && pageTitles?.[citation.page]) || labelFor(ref)
  const Icon = isSource ? Archive : FileText

  function open() {
    if (invalid) return
    if (citation.page) navigate(`/wiki?path=${encodeURIComponent(citation.page)}`)
    else if (citation.source) navigate(`/sources?path=${encodeURIComponent(citation.source)}`)
  }

  return (
    <li className="rounded-lg border bg-card">
      <div className="flex items-center gap-2 px-2.5 py-1.5">
        <span className="text-[11px] font-semibold text-muted-foreground">[{index}]</span>
        {invalid ? (
          <span
            className="flex flex-1 items-center gap-1.5 text-[13px] text-muted-foreground/60 line-through"
            title="Esta citação não corresponde a nenhuma página/fonte do brain"
            data-testid="citation-invalid"
          >
            <AlertTriangle className="size-3.5 shrink-0 text-amber-500" />
            {title}
          </span>
        ) : (
          <button
            onClick={open}
            className="flex flex-1 items-center gap-1.5 text-left text-[13px] text-foreground hover:text-primary"
            data-testid={isSource ? "citation-source" : "citation-page"}
          >
            <Icon className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate">{title}</span>
            <span className="truncate font-mono text-[11px] text-muted-foreground">{ref}</span>
          </button>
        )}
        {citation.quote && (
          <button
            onClick={() => setShowQuote((v) => !v)}
            aria-label="Show quote"
            data-testid="citation-quote-toggle"
            className={cn(
              "shrink-0 rounded p-1 text-muted-foreground hover:text-foreground",
              showQuote && "text-foreground",
            )}
          >
            <Quote className="size-3.5" />
          </button>
        )}
      </div>
      {citation.quote && showQuote && (
        <p
          className="border-t px-2.5 py-1.5 text-[12px] italic text-muted-foreground"
          data-testid="citation-quote"
        >
          “{citation.quote}”
        </p>
      )}
    </li>
  )
}

export interface CitationListProps {
  citations: Citation[]
  /** Optional path → title map to render friendly page titles. */
  pageTitles?: Record<string, string>
}

/** Numbered, clickable citation cards under an answer (#192). Renders nothing
 *  when there are no citations. */
export function CitationList({ citations, pageTitles }: CitationListProps) {
  if (citations.length === 0) return null
  return (
    <div className="mt-3">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Sources
      </div>
      <ul className="space-y-1">
        {citations.map((c, i) => (
          <CitationCard key={i} index={i + 1} citation={c} pageTitles={pageTitles} />
        ))}
      </ul>
    </div>
  )
}
