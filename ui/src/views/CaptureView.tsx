import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/** True when `text` is a single bare URL (quick-capture URL mode, #206). */
export function looksLikeUrl(text: string): boolean {
  const t = text.trim()
  if (!t || /\s/.test(t)) return false
  try {
    const u = new URL(t)
    return u.protocol === "http:" || u.protocol === "https:"
  } catch {
    return false
  }
}

/** Close the quick-capture window. In the Tauri webview this closes the window;
 *  in a browser it's a harmless no-op. */
function closeCapture() {
  try {
    window.close()
  } catch {
    /* no-op in browser */
  }
}

/**
 * Minimal quick-capture screen (#206). Rendered OUTSIDE the AppShell (no
 * sidebar) at /capture. The Tauri shell prefills window.__WIKI_CAPTURE__ from the
 * clipboard and opens this in a small always-on-top window via Cmd+Shift+K.
 */
export function CaptureView() {
  const prefill =
    (globalThis as { __WIKI_CAPTURE__?: string }).__WIKI_CAPTURE__ ?? ""
  const [content, setContent] = useState(prefill)
  const [title, setTitle] = useState("")
  const [busy, setBusy] = useState(false)

  const isUrl = useMemo(() => looksLikeUrl(content), [content])

  // Esc closes without saving.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeCapture()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  async function save(ingest: boolean) {
    const trimmed = content.trim()
    if (!trimmed) {
      toast.error("Nothing to capture")
      return
    }
    setBusy(true)
    try {
      const source = isUrl
        ? await api.addUrlSource(trimmed)
        : await api.addTextSource(title.trim() || "Quick capture", trimmed)
      if (ingest) {
        await api.ingestSource(source.path)
        toast.success("Captured — ingesting in background")
      } else {
        toast.success("Saved to sources")
      }
      // Brief confirmation, then auto-close the capture window.
      setTimeout(closeCapture, 1500)
    } catch {
      toast.error("Could not save capture")
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen w-screen flex-col gap-3 bg-background p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-[14px] font-semibold">Quick capture</h1>
        <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
          {isUrl ? "URL" : "Text"}
        </span>
      </div>

      {!isUrl && (
        <Input
          placeholder="Title (optional)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={busy}
        />
      )}

      <textarea
        autoFocus
        className="flex-1 resize-none rounded-md border bg-transparent p-2 text-[13px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        placeholder="Paste a URL or text to add to the brain…"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        disabled={busy}
      />

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => save(false)}>
          Save source
        </Button>
        <Button size="sm" disabled={busy} onClick={() => save(true)}>
          Save &amp; ingest
        </Button>
      </div>
    </div>
  )
}
