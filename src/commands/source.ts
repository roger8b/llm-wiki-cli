import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { sha256, slugify, today } from "../utils/misc.js";

interface SourceEntry {
  id: string;
  path: string;
  type: string;
  hash: string;
  status: string;
  added_at: string;
}

interface Manifest {
  sources: SourceEntry[];
}

const TYPE_TO_DIR: Record<string, string> = {
  article: "articles",
  book: "books",
  document: "documents",
  transcript: "transcripts",
  spec: "specs",
  image: "images",
  external: "external",
};

async function readManifest(file: string): Promise<Manifest> {
  if (!fs.existsSync(file)) return { sources: [] };
  return (await fs.readJson(file)) as Manifest;
}

export async function sourceAdd(file: string, opts: { type?: string }) {
  const ctx = loadContext();
  const abs = path.resolve(file);
  if (!fs.existsSync(abs)) {
    console.error(pc.red(`file not found: ${file}`));
    process.exitCode = 1;
    return;
  }

  const type = opts.type ?? "article";
  const sub = TYPE_TO_DIR[type] ?? "external";
  const destDir = path.join(ctx.rawDir, sub);
  await fs.ensureDir(destDir);

  const base = path.basename(abs);
  const dest = path.join(destDir, base);
  if (fs.existsSync(dest)) {
    console.log(pc.yellow(`already in raw/: ${path.relative(ctx.root, dest)}`));
  } else {
    await fs.copy(abs, dest);
  }

  const hash = await sha256(dest);
  const slug = slugify(path.parse(base).name);
  const id = `src_${today().replace(/-/g, "")}_${slug}`;

  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  const manifest = await readManifest(manifestPath);

  const existing = manifest.sources.find((s) => s.path === path.relative(ctx.root, dest));
  if (existing) {
    existing.hash = hash;
    console.log(pc.yellow("manifest entry updated."));
  } else {
    manifest.sources.push({
      id,
      path: path.relative(ctx.root, dest),
      type,
      hash,
      status: "pending_ingest",
      added_at: today(),
    });
  }
  await fs.ensureDir(ctx.manifestsDir);
  await fs.writeJson(manifestPath, manifest, { spaces: 2 });

  console.log(pc.green(`✓ source registered: ${path.relative(ctx.root, dest)} (${type})`));
  console.log(pc.dim(`  hash: ${hash}`));
  console.log(pc.dim(`  status: pending_ingest`));
}

export async function sourceList(opts: { status?: string }) {
  const ctx = loadContext();
  const manifest = await readManifest(path.join(ctx.manifestsDir, "sources.json"));
  const rows = opts.status
    ? manifest.sources.filter((s) => s.status === opts.status)
    : manifest.sources;
  if (rows.length === 0) {
    console.log(pc.dim("(no sources)"));
    return;
  }
  for (const s of rows) {
    console.log(`${pc.bold(s.status.padEnd(16))} ${s.type.padEnd(12)} ${s.path}`);
  }
}

export async function sourceStatus(target: string) {
  const ctx = loadContext();
  const manifest = await readManifest(path.join(ctx.manifestsDir, "sources.json"));
  const rel = path.relative(ctx.root, path.resolve(target));
  const s = manifest.sources.find((e) => e.path === rel || e.path === target || e.id === target);
  if (!s) {
    console.log(pc.red(`source not found: ${target}`));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify(s, null, 2));
}

export async function setSourceStatus(rel: string, status: string) {
  const ctx = loadContext();
  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  const manifest = await readManifest(manifestPath);
  const s = manifest.sources.find((e) => e.path === rel);
  if (!s) throw new Error(`source not in manifest: ${rel}`);
  s.status = status;
  await fs.writeJson(manifestPath, manifest, { spaces: 2 });
}

export async function getSourceByPath(rel: string): Promise<SourceEntry | undefined> {
  const ctx = loadContext();
  const manifest = await readManifest(path.join(ctx.manifestsDir, "sources.json"));
  return manifest.sources.find((e) => e.path === rel);
}
