import path from "node:path";
import fs from "fs-extra";
import fg from "fast-glob";
import matter from "gray-matter";
import pc from "picocolors";
import { loadContext, WikiContext } from "../utils/paths.js";

interface PageMeta {
  file: string;
  rel: string;
  type: string;
  title: string;
  slug: string;
  status: string;
  updated_at: string;
  summary?: string;
}

export async function readAllPages(ctx: WikiContext): Promise<PageMeta[]> {
  const files = await fg("**/*.md", { cwd: ctx.wikiDir, absolute: true });
  const pages: PageMeta[] = [];
  for (const f of files) {
    const base = path.basename(f);
    if (base === "index.md" || base === "log.md") continue;
    const raw = await fs.readFile(f, "utf8");
    let parsed: matter.GrayMatterFile<string>;
    try {
      parsed = matter(raw);
    } catch {
      continue;
    }
    const fm = parsed.data as Record<string, any>;
    if (!fm.type) continue;
    const body = parsed.content.trim();
    const firstPara = body.split(/\n\s*\n/).find((p) => !p.startsWith("#"));
    pages.push({
      file: f,
      rel: path.relative(ctx.root, f),
      type: fm.type,
      title: fm.title ?? base,
      slug: fm.slug ?? base.replace(/\.md$/, ""),
      status: fm.status ?? "draft",
      updated_at: String(fm.updated_at ?? ""),
      summary: firstPara?.slice(0, 200),
    });
  }
  return pages;
}

export async function indexRebuild() {
  const ctx = loadContext();
  const pages = await readAllPages(ctx);
  const byType = new Map<string, PageMeta[]>();
  for (const t of ctx.config.page_types) byType.set(t, []);
  for (const p of pages) {
    if (!byType.has(p.type)) byType.set(p.type, []);
    byType.get(p.type)!.push(p);
  }
  for (const arr of byType.values()) arr.sort((a, b) => a.title.localeCompare(b.title));

  const out: string[] = ["# Wiki Index", "", `_Generated ${new Date().toISOString().slice(0, 10)}._`, ""];
  for (const [type, arr] of byType) {
    out.push(`## ${type}`);
    out.push("");
    if (arr.length === 0) {
      out.push("_(empty)_");
    } else {
      for (const p of arr) {
        const linkPath = path.relative(ctx.wikiDir, p.file).replace(/\\/g, "/");
        const tag = p.status !== "draft" ? ` _(${p.status})_` : "";
        const upd = p.updated_at ? ` — ${p.updated_at}` : "";
        out.push(`- [${p.title}](${linkPath})${tag}${upd}`);
      }
    }
    out.push("");
  }
  await fs.writeFile(path.join(ctx.wikiDir, "index.md"), out.join("\n"));
  console.log(pc.green(`✓ index rebuilt: ${pages.length} pages`));
}
