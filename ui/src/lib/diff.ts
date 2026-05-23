// Helpers to feed react-diff-viewer-continued, which wants full old+new
// strings. The backend gives us a unified `diff` + full `new_content`, so we
// reverse-apply the diff onto new_content to reconstruct the old file.

import type { FileChange } from "@/types"

interface Hunk {
  newStart: number // 1-based line in the new file where the hunk begins
  lines: { tag: " " | "+" | "-"; text: string }[]
}

function parseHunks(diff: string): Hunk[] {
  const hunks: Hunk[] = []
  let current: Hunk | null = null
  for (const raw of diff.split("\n")) {
    if (raw.startsWith("@@")) {
      // @@ -oldStart,oldCount +newStart,newCount @@
      const m = /@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw)
      current = { newStart: m ? parseInt(m[1], 10) : 1, lines: [] }
      hunks.push(current)
      continue
    }
    if (!current) continue // skip ---/+++ headers and preamble
    const tag = raw[0]
    if (tag === " " || tag === "+" || tag === "-") {
      current.lines.push({ tag, text: raw.slice(1) })
    }
  }
  return hunks
}

/** Reverse-apply a unified diff to the new content to recover the old content. */
export function reconstructOld(newContent: string, diff: string): string {
  const newLines = newContent.split("\n")
  const oldLines: string[] = []
  let newIdx = 0 // 0-based cursor into newLines

  for (const hunk of parseHunks(diff)) {
    // copy untouched lines before this hunk
    while (newIdx < hunk.newStart - 1 && newIdx < newLines.length) {
      oldLines.push(newLines[newIdx])
      newIdx++
    }
    for (const { tag, text } of hunk.lines) {
      if (tag === " ") {
        oldLines.push(text)
        newIdx++
      } else if (tag === "+") {
        newIdx++ // added in new — absent from old
      } else {
        oldLines.push(text) // removed — present in old only
      }
    }
  }
  // copy any trailing untouched lines
  while (newIdx < newLines.length) {
    oldLines.push(newLines[newIdx])
    newIdx++
  }
  return oldLines.join("\n")
}

/** Derive { oldValue, newValue } for a FileChange. */
export function diffValues(change: FileChange): {
  oldValue: string
  newValue: string
} {
  const newContent = change.new_content ?? ""
  switch (change.operation) {
    case "create":
      return { oldValue: "", newValue: newContent }
    case "delete":
      // no new content; reconstruct the deleted file from the diff body
      return { oldValue: reconstructOld("", change.diff), newValue: "" }
    default:
      return {
        oldValue: reconstructOld(newContent, change.diff),
        newValue: newContent,
      }
  }
}
