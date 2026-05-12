import path from "node:path";
import fs from "fs-extra";
import matter from "gray-matter";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { slugify, today } from "../utils/misc.js";

const TYPE_TO_DIR: Record<string, string> = {
  source: "sources",
  concept: "concepts",
  entity: "entities",
  project: "projects",
  agent: "agents",
  workflow: "workflows",
  decision: "decisions",
  playbook: "playbooks",
  comparison: "comparisons",
  synthesis: "synthesis",
  "open-question": "open-questions",
  glossary: "glossary",
  "lint-report": "synthesis",
};

export async function pageNew(type: string, title: string) {
  const ctx = loadContext();
  if (!ctx.config.page_types.includes(type)) {
    console.error(pc.red(`invalid type: ${type}`));
    process.exitCode = 1;
    return;
  }
  const slug = slugify(title);
  const dir = path.join(ctx.wikiDir, TYPE_TO_DIR[type] ?? type);
  await fs.ensureDir(dir);
  const file = path.join(dir, `${slug}.md`);
  if (fs.existsSync(file)) {
    console.log(pc.yellow(`already exists: ${path.relative(ctx.root, file)}`));
    return;
  }
  const schemaFile = path.join(ctx.schemasDir, `${type}.schema.md`);
  let template = "";
  if (fs.existsSync(schemaFile)) {
    template = await fs.readFile(schemaFile, "utf8");
  } else {
    template = `---\ntype: ${type}\ntitle: ""\nslug: ""\nstatus: draft\ncreated_at: YYYY-MM-DD\nupdated_at: YYYY-MM-DD\n---\n\n# {{title}}\n`;
  }
  template = template
    .replace(/title: ""/g, `title: "${title.replace(/"/g, '\\"')}"`)
    .replace(/slug: ""/g, `slug: "${slug}"`)
    .replace(/created_at: YYYY-MM-DD/g, `created_at: ${today()}`)
    .replace(/updated_at: YYYY-MM-DD/g, `updated_at: ${today()}`)
    .replace(/\{\{title\}\}/g, title);
  await fs.writeFile(file, template);
  console.log(pc.green(`✓ created ${path.relative(ctx.root, file)}`));
}

export interface ValidationIssue {
  file: string;
  level: "error" | "warning";
  message: string;
}

export async function validatePage(file: string): Promise<ValidationIssue[]> {
  const ctx = loadContext();
  const abs = path.resolve(file);
  const rel = path.relative(ctx.root, abs);
  const issues: ValidationIssue[] = [];
  if (!fs.existsSync(abs)) {
    issues.push({ file: rel, level: "error", message: "file not found" });
    return issues;
  }
  const raw = await fs.readFile(abs, "utf8");
  let parsed: matter.GrayMatterFile<string>;
  try {
    parsed = matter(raw);
  } catch (e: any) {
    issues.push({ file: rel, level: "error", message: `frontmatter parse error: ${e.message}` });
    return issues;
  }
  const fm = parsed.data as Record<string, any>;
  if (!fm || Object.keys(fm).length === 0) {
    issues.push({ file: rel, level: "error", message: "missing frontmatter" });
    return issues;
  }
  const required = ["type", "title", "slug", "status", "created_at", "updated_at"];
  for (const k of required) {
    if (!(k in fm) || fm[k] === "" || fm[k] === null || fm[k] === undefined) {
      issues.push({ file: rel, level: "error", message: `missing field: ${k}` });
    }
  }
  if (fm.type && !ctx.config.page_types.includes(fm.type)) {
    issues.push({ file: rel, level: "error", message: `invalid type: ${fm.type}` });
  }
  if (fm.status && !ctx.config.statuses.includes(fm.status)) {
    issues.push({ file: rel, level: "error", message: `invalid status: ${fm.status}` });
  }
  if (
    (fm.status === "reviewed" || fm.status === "canonical") &&
    (!Array.isArray(fm.sources) || fm.sources.length === 0)
  ) {
    issues.push({
      file: rel,
      level: "warning",
      message: `status ${fm.status} requires non-empty sources`,
    });
  }
  return issues;
}

export async function pageValidate(file: string) {
  const issues = await validatePage(file);
  if (issues.length === 0) {
    console.log(pc.green("✓ valid"));
    return;
  }
  for (const i of issues) {
    const tag = i.level === "error" ? pc.red("error") : pc.yellow("warn");
    console.log(`${tag} ${i.file}: ${i.message}`);
  }
  if (issues.some((i) => i.level === "error")) process.exitCode = 1;
}

async function readInput(file?: string): Promise<string> {
  if (file && file !== "-") {
    const abs = path.resolve(file);
    if (!fs.existsSync(abs)) throw new Error(`file not found: ${file}`);
    return fs.readFile(abs, "utf8");
  }
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

export async function pageSave(opts: {
  type: string;
  title: string;
  file?: string;
  status?: string;
  sources?: string[];
  related?: string[];
  tags?: string[];
  force?: boolean;
}) {
  const ctx = loadContext();
  if (!ctx.config.page_types.includes(opts.type)) {
    console.error(pc.red(`invalid type: ${opts.type}`));
    process.exitCode = 1;
    return;
  }
  const content = await readInput(opts.file);
  const slug = slugify(opts.title);
  const dir = path.join(ctx.wikiDir, TYPE_TO_DIR[opts.type] ?? opts.type);
  await fs.ensureDir(dir);
  const dest = path.join(dir, `${slug}.md`);
  if (fs.existsSync(dest) && !opts.force) {
    console.error(pc.red(`already exists: ${slug} (use --force or 'wiki page update')`));
    process.exitCode = 1;
    return;
  }
  let body = content;
  let existingFm: Record<string, any> = {};
  try {
    const parsed = matter(content);
    if (Object.keys(parsed.data).length > 0) {
      existingFm = parsed.data as Record<string, any>;
      body = parsed.content;
    }
  } catch { /* ignore */ }
  const fm: Record<string, any> = {
    type: opts.type,
    title: opts.title,
    slug,
    status: opts.status ?? existingFm.status ?? "draft",
    created_at: normalizeDate(existingFm.created_at) ?? today(),
    updated_at: today(),
    sources: opts.sources ?? existingFm.sources ?? [],
    related: opts.related ?? existingFm.related ?? [],
    tags: opts.tags ?? existingFm.tags ?? [],
  };
  if (existingFm.confidence) fm.confidence = existingFm.confidence;
  if (existingFm.raw_path) fm.raw_path = existingFm.raw_path;
  if (existingFm.source_hash) fm.source_hash = existingFm.source_hash;
  await fs.writeFile(dest, matter.stringify(body.trimStart(), fm));
  console.log(pc.green(`✓ saved: ${opts.type}/${slug}`));
}

function normalizeDate(v: any): string | undefined {
  if (v == null) return undefined;
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  if (typeof v === "string") {
    const m = v.match(/^(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  return undefined;
}

export async function pageUpdate(slug: string, opts: { file?: string; status?: string }) {
  const ctx = loadContext();
  const files = await import("fast-glob").then((m) =>
    m.default("**/*.md", { cwd: ctx.wikiDir, absolute: true }),
  );
  let target: string | undefined;
  for (const f of files) {
    if (path.basename(f) === "index.md" || path.basename(f) === "log.md") continue;
    const parsed = matter(await fs.readFile(f, "utf8"));
    if (parsed.data.slug === slug) {
      target = f;
      break;
    }
  }
  if (!target) {
    console.error(pc.red(`page not found: ${slug}`));
    process.exitCode = 1;
    return;
  }
  const content = await readInput(opts.file);
  const existing = matter(await fs.readFile(target, "utf8"));
  let body = content;
  let incomingFm: Record<string, any> = {};
  try {
    const parsed = matter(content);
    if (Object.keys(parsed.data).length > 0) {
      incomingFm = parsed.data as Record<string, any>;
      body = parsed.content;
    }
  } catch { /* ignore */ }
  // preserve existing body if incoming body is empty (frontmatter-only patch)
  if (!body.trim()) body = existing.content;
  const merged: Record<string, any> = {
    ...existing.data,
    ...incomingFm,
    updated_at: today(),
    ...(opts.status ? { status: opts.status } : {}),
  };
  if (merged.created_at) merged.created_at = normalizeDate(merged.created_at) ?? today();
  const fm = merged;
  await fs.writeFile(target, matter.stringify(body.trimStart(), fm));
  console.log(pc.green(`✓ updated: ${slug}`));
}
