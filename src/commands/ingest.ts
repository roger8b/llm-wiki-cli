import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { sha256, today } from "../utils/misc.js";
import { searchWiki } from "./search.js";
import { setSourceStatus, getSourceByPath } from "./source.js";
import { readAllPages } from "./index.js";

export async function ingestPrepare(sourcePath: string) {
  const ctx = loadContext();
  let abs = path.resolve(sourcePath);
  if (!fs.existsSync(abs)) {
    abs = path.resolve(ctx.root, sourcePath);
  }
  if (!fs.existsSync(abs)) {
    console.error(pc.red(`source not found: ${sourcePath}`));
    process.exitCode = 1;
    return;
  }
  const rel = path.relative(ctx.root, abs);
  if (!rel.startsWith(path.relative(ctx.root, ctx.rawDir))) {
    console.error(pc.red(`source must live under ${path.relative(ctx.root, ctx.rawDir)}/`));
    process.exitCode = 1;
    return;
  }

  const meta = await getSourceByPath(rel);
  const hash = await sha256(abs);
  const sample = (await fs.readFile(abs, "utf8")).slice(0, 4000);
  const headTerms = path.parse(abs).name.split(/[-_\s]+/).filter((t) => t.length > 3);
  const related = new Set<string>();
  for (const t of headTerms) {
    const hits = await searchWiki(t);
    for (const h of hits.slice(0, 5)) related.add(h.rel);
  }

  const ctxLines: string[] = [
    `# Ingest context — ${path.basename(abs)}`,
    "",
    `Generated: ${today()}`,
    "",
    "## Target source",
    "",
    `- path: \`${rel}\``,
    `- type: ${meta?.type ?? "unknown"}`,
    `- hash: ${hash}`,
    `- status: ${meta?.status ?? "unknown"}`,
    "",
    "## Protocol",
    "",
    `Read \`WIKI_PROTOCOL.md\`, \`wiki/index.md\`, and the \`wiki-ingest\` skill before processing.`,
    "",
    "## Schemas to apply",
    "",
    "- `schemas/source.schema.md` → create `wiki/sources/<slug>.md`",
    "- `schemas/concept.schema.md` → update/create `wiki/concepts/*`",
    "- `schemas/synthesis.schema.md` → update/create `wiki/synthesis/*` when applicable",
    "",
    "## Potentially related pages",
    "",
    related.size === 0 ? "_(none found via heuristic search)_" : Array.from(related).map((r) => `- \`${r}\``).join("\n"),
    "",
    "## Checklist for the agent",
    "",
    "- [ ] read source",
    "- [ ] create `wiki/sources/<slug>.md` with frontmatter (source.schema)",
    "- [ ] extract concepts and update/create concept pages",
    "- [ ] flag contradictions vs existing pages",
    "- [ ] update `wiki/index.md`",
    "- [ ] append entry to `wiki/log.md` (operation: ingest)",
    "- [ ] do NOT modify the raw source file",
    "",
    "## Source sample (first 4000 chars)",
    "",
    "```",
    sample,
    "```",
    "",
    "## Final instruction",
    "",
    "Process the source above into the wiki following the steps. Use `llm-wiki ingest commit` afterwards to validate.",
    "",
  ];

  await fs.ensureDir(ctx.cacheDir);
  const outPath = path.join(ctx.cacheDir, "ingest-context.md");
  await fs.writeFile(outPath, ctxLines.join("\n"));
  console.log(pc.green(`✓ ingest context written: ${path.relative(ctx.root, outPath)}`));
}

export async function ingestCommit(sourcePath: string) {
  const ctx = loadContext();
  let abs = path.resolve(sourcePath);
  if (!fs.existsSync(abs)) {
    abs = path.resolve(ctx.root, sourcePath);
  }
  const rel = path.relative(ctx.root, abs);
  const meta = await getSourceByPath(rel);
  if (!meta) {
    console.error(pc.red(`source not registered: ${rel}`));
    process.exitCode = 1;
    return;
  }

  const issues: string[] = [];

  const currentHash = await sha256(abs);
  if (currentHash !== meta.hash) {
    issues.push(`raw source hash changed (was immutable): ${rel}`);
  }

  const pages = await readAllPages(ctx);
  const sourcePages = pages.filter((p) => p.type === "source");
  const slug = path.parse(abs).name.toLowerCase();
  const sourcePage = sourcePages.find(
    (p) => p.rel.includes(slug) || p.slug.includes(slug),
  );
  if (!sourcePage) {
    issues.push("no matching source summary page found under wiki/sources/");
  }

  const logPath = path.join(ctx.wikiDir, "log.md");
  if (fs.existsSync(logPath)) {
    const log = await fs.readFile(logPath, "utf8");
    if (!log.includes(rel) && !log.includes(slug)) {
      issues.push("no log entry references this ingest");
    }
  } else {
    issues.push("wiki/log.md missing");
  }

  if (issues.length > 0) {
    for (const i of issues) console.log(pc.red("✗ ") + i);
    console.log(pc.red("\ningest commit failed."));
    process.exitCode = 1;
    return;
  }

  await setSourceStatus(rel, "ingested");
  console.log(pc.green(`✓ ingest committed: ${rel} → status=ingested`));
}
