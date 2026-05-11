import path from "node:path";
import fs from "fs-extra";
import matter from "gray-matter";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { searchWiki } from "./search.js";
import { slugify, today } from "../utils/misc.js";

export async function queryPrepare(question: string) {
  const ctx = loadContext();
  const hits = await searchWiki(question);
  const top = hits.slice(0, 10);

  const lines: string[] = [
    `# Query context`,
    "",
    `Generated: ${today()}`,
    "",
    "## Question",
    "",
    `> ${question}`,
    "",
    "## Candidate pages",
    "",
  ];
  if (top.length === 0) {
    lines.push("_(no candidates found via search)_");
  } else {
    for (const h of top) {
      lines.push(`- \`${h.rel}\` — ${h.type}/${h.status} — ${h.title}`);
      if (h.excerpt) lines.push(`  > ${h.excerpt}`);
    }
  }
  lines.push("", "## Decisions to consider", "");
  const decisions = hits.filter((h) => h.type === "decision");
  if (decisions.length === 0) lines.push("_(no related decisions found)_");
  else for (const d of decisions) lines.push(`- \`${d.rel}\` — ${d.status}`);

  lines.push("", "## Open questions nearby", "");
  const open = hits.filter((h) => h.type === "open-question");
  if (open.length === 0) lines.push("_(none)_");
  else for (const o of open) lines.push(`- \`${o.rel}\``);

  lines.push(
    "",
    "## Instructions for the agent",
    "",
    "1. Read the candidate pages above (prioritize canonical/reviewed).",
    "2. Inspect raw sources under `raw/` if evidence is weak.",
    "3. Answer the question grounded in the wiki, citing pages.",
    "4. Separate fact from inference.",
    "5. If the answer is durable, save it with `llm-wiki query save <file> --as synthesis --title \"...\"`.",
    "",
  );

  await fs.ensureDir(ctx.cacheDir);
  const out = path.join(ctx.cacheDir, "query-context.md");
  await fs.writeFile(out, lines.join("\n"));
  console.log(pc.green(`✓ query context written: ${path.relative(ctx.root, out)}`));
}

const TYPE_TO_DIR: Record<string, string> = {
  synthesis: "synthesis",
  comparison: "comparisons",
  playbook: "playbooks",
  decision: "decisions",
  "open-question": "open-questions",
  concept: "concepts",
};

export async function querySave(file: string, opts: { as: string; title: string }) {
  const ctx = loadContext();
  const abs = path.resolve(file);
  if (!fs.existsSync(abs)) {
    console.error(pc.red(`file not found: ${file}`));
    process.exitCode = 1;
    return;
  }
  if (!ctx.config.page_types.includes(opts.as)) {
    console.error(pc.red(`invalid type: ${opts.as}`));
    process.exitCode = 1;
    return;
  }
  const slug = slugify(opts.title);
  const dir = path.join(ctx.wikiDir, TYPE_TO_DIR[opts.as] ?? opts.as);
  await fs.ensureDir(dir);
  const dest = path.join(dir, `${slug}.md`);
  if (fs.existsSync(dest)) {
    console.error(pc.red(`already exists: ${path.relative(ctx.root, dest)}`));
    process.exitCode = 1;
    return;
  }
  const raw = await fs.readFile(abs, "utf8");
  let body = raw;
  let existingFm: Record<string, any> = {};
  try {
    const parsed = matter(raw);
    if (Object.keys(parsed.data).length > 0) {
      existingFm = parsed.data as Record<string, any>;
      body = parsed.content;
    }
  } catch {
    /* ignore */
  }

  const fm = {
    type: opts.as,
    title: opts.title,
    slug,
    status: existingFm.status ?? "draft",
    confidence: existingFm.confidence ?? "medium",
    created_at: today(),
    updated_at: today(),
    sources: existingFm.sources ?? [],
    related: existingFm.related ?? [],
    tags: existingFm.tags ?? [],
  };

  const out = matter.stringify(body.trimStart(), fm);
  await fs.writeFile(dest, out);

  const logPath = path.join(ctx.wikiDir, "log.md");
  const entry = `\n## [${today()}] query | ${opts.title}\n- files: ${path.relative(ctx.root, dest)}\n- notes: saved via llm-wiki query save\n`;
  await fs.appendFile(logPath, entry);

  console.log(pc.green(`✓ saved ${path.relative(ctx.root, dest)}`));
}
