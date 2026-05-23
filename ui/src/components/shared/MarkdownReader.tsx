import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import "highlight.js/styles/github.css"
import { cn } from "@/lib/utils"

interface MarkdownReaderProps {
  content: string
  className?: string
  /** Called when a [[Wiki Link]] is clicked, with the link text. */
  onWikiLink?: (title: string) => void
}

const WIKILINK_HREF = "wikilink:"

/** Turn `[[Page Title]]` into a markdown link with a custom scheme. */
function preprocessWikilinks(md: string): string {
  return md.replace(/\[\[([^\]]+)\]\]/g, (_m, title: string) => {
    const t = title.trim()
    return `[${t}](${WIKILINK_HREF}${encodeURIComponent(t)})`
  })
}

export function MarkdownReader({
  content,
  className,
  onWikiLink,
}: MarkdownReaderProps) {
  return (
    <div className={cn("prose-wiki", className)}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          a({ href, children, ...props }) {
            if (href?.startsWith(WIKILINK_HREF)) {
              const title = decodeURIComponent(href.slice(WIKILINK_HREF.length))
              return (
                <button
                  type="button"
                  className="wikilink"
                  onClick={() => onWikiLink?.(title)}
                >
                  {children}
                </button>
              )
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" {...props}>
                {children}
              </a>
            )
          },
        }}
      >
        {preprocessWikilinks(content)}
      </Markdown>
    </div>
  )
}
