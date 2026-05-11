import path from "node:path";
import fs from "fs-extra";
import fg from "fast-glob";
import matter from "gray-matter";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";

export interface SearchHit {
  file: string;
  rel: string;
  title: string;
  type: string;
  status: string;
  score: number;
  excerpt: string;
}

export async function searchWiki(
  query: string,
  filter: { type?: string; status?: string } = {},
): Promise<SearchHit[]> {
  const ctx = loadContext();
  const q = query.toLowerCase();
  const terms = q.split(/\s+/).filter(Boolean);
  const files = await fg("**/*.md", { cwd: ctx.wikiDir, absolute: true });
  const hits: SearchHit[] = [];
  for (const f of files) {
    const raw = await fs.readFile(f, "utf8");
    let parsed: matter.GrayMatterFile<string>;
    try {
      parsed = matter(raw);
    } catch {
      continue;
    }
    const fm = parsed.data as Record<string, any>;
    if (filter.type && fm.type !== filter.type) continue;
    if (filter.status && fm.status !== filter.status) continue;
    const haystack = (parsed.content + " " + (fm.title ?? "") + " " + (fm.tags ?? []).join(" ")).toLowerCase();
    let score = 0;
    for (const t of terms) {
      const count = haystack.split(t).length - 1;
      score += count;
      if ((fm.title ?? "").toLowerCase().includes(t)) score += 5;
      if ((fm.slug ?? "").toLowerCase().includes(t)) score += 3;
    }
    if (fm.status === "canonical") score += 2;
    else if (fm.status === "reviewed") score += 1;
    if (score === 0) continue;
    const idx = haystack.indexOf(terms[0] ?? "");
    const excerpt = parsed.content
      .slice(Math.max(0, idx - 60), idx + 120)
      .replace(/\n+/g, " ")
      .trim();
    hits.push({
      file: f,
      rel: path.relative(ctx.root, f),
      title: fm.title ?? path.basename(f),
      type: fm.type ?? "",
      status: fm.status ?? "",
      score,
      excerpt,
    });
  }
  hits.sort((a, b) => b.score - a.score);
  return hits;
}

export async function searchCmd(query: string, opts: { type?: string; status?: string }) {
  const hits = await searchWiki(query, opts);
  if (hits.length === 0) {
    console.log(pc.dim("no matches"));
    return;
  }
  for (const h of hits.slice(0, 30)) {
    console.log(
      `${pc.bold(h.title)}  ${pc.dim(h.type + "/" + h.status)}  score=${h.score}`,
    );
    console.log(`  ${pc.dim(h.rel)}`);
    if (h.excerpt) console.log(`  ${h.excerpt}`);
  }
}
