import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued"
import type { FileChange } from "@/types"
import { diffValues } from "@/lib/diff"

// Light diff theme — blends with the app and stays clearly bounded.
const lightStyles = {
  variables: {
    light: {
      diffViewerBackground: "#ffffff",
      diffViewerColor: "#1f2328",
      addedBackground: "#e6ffec",
      addedColor: "#1a7f37",
      removedBackground: "#ffebe9",
      removedColor: "#cf222e",
      wordAddedBackground: "#abf2bc",
      wordRemovedBackground: "#ffc1c0",
      gutterBackground: "#f6f8fa",
      gutterColor: "#8c959f",
      addedGutterBackground: "#ccffd8",
      removedGutterBackground: "#ffd7d5",
      codeFoldBackground: "#f6f8fa",
      emptyLineBackground: "#fafbfc",
    },
  },
  contentText: {
    fontFamily: "var(--font-mono)",
    fontSize: "12px",
    lineHeight: "1.6",
  },
  gutter: {
    fontFamily: "var(--font-mono)",
    fontSize: "11px",
    minWidth: "32px",
  },
}

interface DiffPanelProps {
  change: FileChange
  splitView?: boolean
}

export function DiffPanel({ change, splitView = false }: DiffPanelProps) {
  const { oldValue, newValue } = diffValues(change)
  return (
    <div className="min-h-0 flex-1 overflow-hidden p-3">
      {/* Bounded card: own border on every side (incl. right) so the diff
          never looks like it bleeds off-screen. Scrolls inside. */}
      <div className="diff-scroll h-full overflow-auto rounded-md border bg-card">
        <div className="sticky top-0 z-10 border-b bg-muted px-4 py-2 font-mono text-[12px] text-muted-foreground">
          {change.path}
        </div>
        <ReactDiffViewer
          oldValue={oldValue}
          newValue={newValue}
          splitView={splitView}
          compareMethod={DiffMethod.WORDS}
          hideLineNumbers={false}
          styles={lightStyles}
        />
      </div>
    </div>
  )
}
