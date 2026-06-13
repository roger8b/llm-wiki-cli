import type { PageType } from "@/types"

/**
 * ASCII kebab-case slug — parity with the backend `core.markdown.slugify`:
 * NFKD normalize -> drop non-ASCII (mirrors `.encode("ascii","ignore")`) ->
 * lowercase -> collapse non-alphanumerics to "-" -> trim "-". Used to preview
 * the path of a new page before saving (#187).
 */
export function slugify(value: string): string {
  const ascii = Array.from(value.normalize("NFKD"))
    .filter((ch) => (ch.codePointAt(0) ?? 0) < 0x80)
    .join("")
  return ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

/** Page type -> wiki subdirectory (mirrors page_service.DIR). */
export const TYPE_DIR: Record<PageType, string> = {
  concept: "concepts",
  entity: "entities",
  source_summary: "research",
  synthesis: "synthesis",
  decision: "decisions",
  project: "projects",
  research: "research",
}

/** Full wiki path for a new page of a given type/title. */
export function pagePath(type: PageType, title: string): string {
  return `wiki/${TYPE_DIR[type]}/${slugify(title)}.md`
}
