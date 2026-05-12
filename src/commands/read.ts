import path from "node:path";
import fs from "fs-extra";
import fg from "fast-glob";
import matter from "gray-matter";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { readAllPages } from "./index.js";

// ── protocol ─────────────────────────────────────────────────────────────────

export async function protocolShow() {
  const ctx = loadContext();
  const file = path.join(ctx.root, "WIKI_PROTOCOL.md");
  if (!fs.existsSync(file)) {
    console.error(pc.red("WIKI_PROTOCOL.md not found in brain"));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(file, "utf8"));
}

// ── schema ───────────────────────────────────────────────────────────────────

export async function schemaList() {
  const ctx = loadContext();
  const files = await fg("*.schema.md", { cwd: ctx.schemasDir });
  if (files.length === 0) {
    console.log(pc.dim("(no schemas)"));
    return;
  }
  for (const f of files.sort()) {
    const type = f.replace(/\.schema\.md$/, "");
    console.log(type);
  }
}

export async function schemaShow(type: string) {
  const ctx = loadContext();
  const file = path.join(ctx.schemasDir, `${type}.schema.md`);
  if (!fs.existsSync(file)) {
    console.error(pc.red(`schema not found: ${type}`));
    console.error(pc.dim("run `wiki schema list` to see available types"));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(file, "utf8"));
}

// ── page ─────────────────────────────────────────────────────────────────────

export async function pageList(opts: { type?: string; status?: string }) {
  const ctx = loadContext();
  const pages = await readAllPages(ctx);
  let rows = pages;
  if (opts.type) rows = rows.filter((p) => p.type === opts.type);
  if (opts.status) rows = rows.filter((p) => p.status === opts.status);
  if (rows.length === 0) {
    console.log(pc.dim("(no pages match)"));
    return;
  }
  rows.sort((a, b) => a.type.localeCompare(b.type) || a.title.localeCompare(b.title));
  for (const p of rows) {
    console.log(
      `${pc.bold(p.type.padEnd(15))} ${p.status.padEnd(10)} ${p.slug.padEnd(40)} ${p.title}`,
    );
  }
}

export async function pageShow(target: string) {
  const ctx = loadContext();
  const pages = await readAllPages(ctx);
  // try slug match first, then path match, then partial slug
  let match =
    pages.find((p) => p.slug === target) ||
    pages.find((p) => p.rel === target || p.rel.endsWith(target)) ||
    pages.find((p) => p.slug.includes(target));
  if (!match) {
    console.error(pc.red(`page not found: ${target}`));
    console.error(pc.dim("run `wiki page list` to see available pages"));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(match.file, "utf8"));
}

// ── index ────────────────────────────────────────────────────────────────────

export async function indexShow() {
  const ctx = loadContext();
  const file = path.join(ctx.wikiDir, "index.md");
  if (!fs.existsSync(file)) {
    console.error(pc.red("index.md not found — run `wiki index rebuild`"));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(file, "utf8"));
}

// ── log ──────────────────────────────────────────────────────────────────────

export async function logShow(opts: { last?: string }) {
  const ctx = loadContext();
  const file = path.join(ctx.wikiDir, "log.md");
  if (!fs.existsSync(file)) {
    console.log(pc.dim("(empty log)"));
    return;
  }
  const content = await fs.readFile(file, "utf8");
  const last = opts.last ? parseInt(opts.last, 10) : undefined;
  if (!last || isNaN(last)) {
    process.stdout.write(content);
    return;
  }
  // split by "## [" entries and take last N
  const parts = content.split(/(?=^## \[)/m);
  const header = parts[0];
  const entries = parts.slice(1);
  const recent = entries.slice(-last);
  process.stdout.write(header + recent.join(""));
}

// ── source ───────────────────────────────────────────────────────────────────

export async function sourceShow(target: string) {
  const ctx = loadContext();
  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  const manifest = fs.existsSync(manifestPath)
    ? ((await fs.readJson(manifestPath)) as { sources: any[] })
    : { sources: [] };
  // match by id, by path, by basename
  const match =
    manifest.sources.find((s: any) => s.id === target) ||
    manifest.sources.find((s: any) => s.path === target) ||
    manifest.sources.find((s: any) => path.basename(s.path) === target) ||
    manifest.sources.find((s: any) => s.path.endsWith(target));
  if (!match) {
    console.error(pc.red(`source not found: ${target}`));
    console.error(pc.dim("run `wiki source list` to see available sources"));
    process.exitCode = 1;
    return;
  }
  const abs = path.join(ctx.root, match.path);
  if (!fs.existsSync(abs)) {
    console.error(pc.red(`source file missing on disk: ${match.path}`));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(abs, "utf8"));
}

// ── ingest context ───────────────────────────────────────────────────────────

export async function ingestContextShow() {
  const ctx = loadContext();
  const file = path.join(ctx.cacheDir, "ingest-context.md");
  if (!fs.existsSync(file)) {
    console.error(pc.red("no ingest context — run `wiki ingest prepare <source>` first"));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(file, "utf8"));
}

// ── query context ────────────────────────────────────────────────────────────

export async function queryContextShow() {
  const ctx = loadContext();
  const file = path.join(ctx.cacheDir, "query-context.md");
  if (!fs.existsSync(file)) {
    console.error(pc.red('no query context — run `wiki query prepare "<question>"` first'));
    process.exitCode = 1;
    return;
  }
  process.stdout.write(await fs.readFile(file, "utf8"));
}
