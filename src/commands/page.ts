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
