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
  const matter = (await import("gray-matter")).default;
  const { validatePage } = await import("./page.js");

  // 1. raw source hash must be unchanged
  const currentHash = await sha256(abs);
  if (currentHash !== meta.hash) {
    issues.push(`raw source hash changed (sources are immutable): ${rel}`);
  }

  // 2. find the source page that references this raw path
  const pages = await readAllPages(ctx);
  const sourcePages = pages.filter((p) => p.type === "source");
  let sourcePage = null;
  for (const sp of sourcePages) {
    const raw = await fs.readFile(sp.file, "utf8");
    const fm = matter(raw).data as Record<string, any>;
    if (fm.raw_path === rel) {
      sourcePage = { ...sp, fm };
      break;
    }
  }

  if (!sourcePage) {
    issues.push(
      `no source page has raw_path = "${rel}" — create one with \`wiki page save --type source\``,
    );
  } else {
    // 3. validate source page frontmatter via wiki page validate
    const validation = await validatePage(sourcePage.file);
    for (const v of validation) {
      if (v.level === "error") {
        issues.push(`source page invalid: ${v.message}`);
      }
    }

    // 4. source_hash on the page must match the manifest hash
    if (!sourcePage.fm.source_hash) {
      issues.push(`source page missing source_hash field`);
    } else if (sourcePage.fm.source_hash !== meta.hash) {
      issues.push(
        `source page source_hash does not match manifest:\n      page:     ${sourcePage.fm.source_hash}\n      manifest: ${meta.hash}`,
      );
    }

    // 5. date fields must be YYYY-MM-DD strings (not ISO datetimes or Date objects)
    for (const field of ["created_at", "updated_at"]) {
      const val = sourcePage.fm[field];
      if (val instanceof Date || (typeof val === "string" && /T\d{2}:/.test(val))) {
        issues.push(
          `source page ${field} must be YYYY-MM-DD string, got: ${val instanceof Date ? val.toISOString() : val}`,
        );
      }
    }
  }

  // 6. related/sources on the source page must be valid slugs of existing pages
  if (sourcePage) {
    const allSlugs = new Set(pages.map((p) => p.slug));
    for (const field of ["related", "sources"] as const) {
      const refs = sourcePage.fm[field];
      if (!Array.isArray(refs)) continue;
      for (const ref of refs) {
        if (typeof ref !== "string") continue;
        if (ref.includes("/") || ref.endsWith(".md")) {
          issues.push(
            `source page ${field}[] must be slugs (not paths): "${ref}" — use the slug like "broker-local-pi-intercom"`,
          );
          continue;
        }
        if (!allSlugs.has(ref)) {
          issues.push(`source page ${field}[] references unknown slug: "${ref}"`);
        }
      }
    }
  }

  // 7. validate every page created during this ingest (concepts, etc) that has source_hash matching
  const ingestedPages = pages.filter((p) => p.type !== "source").filter((p) => {
    try {
      const raw = fs.readFileSync(p.file, "utf8");
      const fm = matter(raw).data as Record<string, any>;
      const sources = Array.isArray(fm.sources) ? fm.sources : [];
      return sources.some((s: any) => typeof s === "string" && (s === sourcePage?.slug || s === rel));
    } catch {
      return false;
    }
  });
  const allSlugs = new Set(pages.map((p) => p.slug));
  for (const ip of ingestedPages) {
    const raw = fs.readFileSync(ip.file, "utf8");
    const fm = matter(raw).data as Record<string, any>;
    for (const field of ["related", "sources"] as const) {
      const refs = fm[field];
      if (!Array.isArray(refs)) continue;
      for (const ref of refs) {
        if (typeof ref !== "string") continue;
        if (ref.includes("/") || ref.endsWith(".md")) {
          issues.push(
            `page "${ip.slug}" ${field}[] must be slugs (not paths): "${ref}"`,
          );
          continue;
        }
        if (!allSlugs.has(ref)) {
          issues.push(`page "${ip.slug}" ${field}[] references unknown slug: "${ref}"`);
        }
      }
    }
  }

  // 8. log must reference the source
  const logPath = path.join(ctx.wikiDir, "log.md");
  if (fs.existsSync(logPath)) {
    const log = await fs.readFile(logPath, "utf8");
    const slug = path.parse(abs).name.toLowerCase();
    if (!log.includes(rel) && !log.includes(slug)) {
      issues.push(`no log entry references this ingest — append one with \`wiki log add\``);
    }
  } else {
    issues.push("wiki/log.md missing");
  }

  if (issues.length > 0) {
    for (const i of issues) console.log(pc.red("✗ ") + i);
    console.log(pc.red(`\ningest commit failed (${issues.length} issue${issues.length === 1 ? "" : "s"}).`));
    process.exitCode = 1;
    return;
  }

  await setSourceStatus(rel, "ingested");
  console.log(pc.green(`✓ ingest committed: ${rel} → status=ingested`));
}
