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
  let s = manifest.sources.find((e) => e.path === rel || e.path === target || e.id === target);
  if (!s) {
    // fallback: treat target as a wiki page slug and resolve raw_path from its frontmatter
    const fgMod = await import("fast-glob");
    const matter = (await import("gray-matter")).default;
    const files = await fgMod.default("**/*.md", { cwd: ctx.wikiDir, absolute: true });
    for (const f of files) {
      try {
        const data = matter(await fs.readFile(f, "utf8")).data as Record<string, any>;
        if (data.slug === target && typeof data.raw_path === "string") {
          s = manifest.sources.find((e) => e.path === data.raw_path);
          if (s) break;
        }
      } catch { /* ignore */ }
    }
  }
  if (!s) {
    console.log(pc.red(`source not found: ${target}`));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify(s, null, 2));
}

function findSourceEntry(manifest: Manifest, target: string, root: string): SourceEntry | undefined {
  const rel = path.relative(root, path.resolve(target));
  return manifest.sources.find((e) => e.path === rel || e.path === target || e.id === target);
}

export async function sourceRehash(target: string) {
  const ctx = loadContext();
  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  const manifest = await readManifest(manifestPath);
  const entry = findSourceEntry(manifest, target, ctx.root);
  if (!entry) {
    console.error(pc.red(`source not found in manifest: ${target}`));
    process.exitCode = 1;
    return;
  }
  const abs = path.join(ctx.root, entry.path);
  if (!fs.existsSync(abs)) {
    console.error(pc.red(`raw file missing on disk: ${entry.path}`));
    process.exitCode = 1;
    return;
  }
  const newHash = await sha256(abs);
  const oldHash = entry.hash;
  if (newHash === oldHash) {
    console.log(pc.dim(`hash unchanged: ${newHash}`));
    return;
  }
  entry.hash = newHash;
  await fs.writeJson(manifestPath, manifest, { spaces: 2 });
  // also update source page frontmatter, if one exists
  const fgMod = await import("fast-glob");
  const matter = (await import("gray-matter")).default;
  const files = await fgMod.default("sources/**/*.md", { cwd: ctx.wikiDir, absolute: true });
  for (const f of files) {
    try {
      const parsed = matter(await fs.readFile(f, "utf8"));
      const data = parsed.data as Record<string, any>;
      if (data.raw_path === entry.path && data.source_hash !== newHash) {
        data.source_hash = newHash;
        data.updated_at = today();
        await fs.writeFile(f, matter.stringify(parsed.content.trimStart(), data));
        console.log(pc.dim(`  updated source page frontmatter: ${path.relative(ctx.root, f)}`));
      }
    } catch { /* ignore */ }
  }
  console.log(pc.green(`✓ rehashed ${entry.path}`));
  console.log(pc.dim(`  old: ${oldHash}`));
  console.log(pc.dim(`  new: ${newHash}`));
}

export async function sourceRemove(target: string, opts: { force?: boolean; keepRaw?: boolean }) {
  const ctx = loadContext();
  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  const manifest = await readManifest(manifestPath);
  const entry = findSourceEntry(manifest, target, ctx.root);
  if (!entry) {
    console.error(pc.red(`source not found in manifest: ${target}`));
    process.exitCode = 1;
    return;
  }
  // refuse if a non-deprecated wiki source page still references this raw_path
  const fgMod = await import("fast-glob");
  const matter = (await import("gray-matter")).default;
  const files = await fgMod.default("sources/**/*.md", { cwd: ctx.wikiDir, absolute: true });
  const referencing: { file: string; slug: string; status: string }[] = [];
  for (const f of files) {
    try {
      const data = matter(await fs.readFile(f, "utf8")).data as Record<string, any>;
      if (data.raw_path === entry.path) {
        referencing.push({ file: f, slug: data.slug, status: data.status ?? "draft" });
      }
    } catch { /* ignore */ }
  }
  const live = referencing.filter((r) => r.status !== "deprecated");
  if (live.length > 0 && !opts.force) {
    console.error(pc.red(`refusing to remove: source is referenced by ${live.length} non-deprecated page(s):`));
    for (const r of live) console.error(pc.dim(`  ${path.relative(ctx.root, r.file)} (slug=${r.slug}, status=${r.status})`));
    console.error(pc.dim("deprecate or delete those pages first, or pass --force"));
    process.exitCode = 1;
    return;
  }
  // remove manifest entry
  const before = manifest.sources.length;
  manifest.sources = manifest.sources.filter((s) => s !== entry);
  await fs.writeJson(manifestPath, manifest, { spaces: 2 });
  console.log(pc.green(`✓ manifest entry removed (${before} → ${manifest.sources.length} sources)`));
  // remove raw file unless --keep-raw
  const abs = path.join(ctx.root, entry.path);
  if (!opts.keepRaw && fs.existsSync(abs)) {
    await fs.remove(abs);
    console.log(pc.green(`✓ raw file removed: ${entry.path}`));
  } else if (opts.keepRaw) {
    console.log(pc.dim(`  raw file kept: ${entry.path}`));
  }
  if (referencing.length > 0) {
    console.log(pc.yellow(`note: ${referencing.length} source page(s) still reference this raw_path (all deprecated):`));
    for (const r of referencing) console.log(pc.dim(`  ${path.relative(ctx.root, r.file)}`));
    console.log(pc.dim("clean them up with `wiki page delete <slug>` when ready"));
  }
}

export async function sourceVerify() {
  const ctx = loadContext();
  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  const manifest = await readManifest(manifestPath);
  let drift = 0;
  let missing = 0;
  for (const entry of manifest.sources) {
    const abs = path.join(ctx.root, entry.path);
    if (!fs.existsSync(abs)) {
      console.log(pc.red(`✗ missing: ${entry.path}`));
      missing++;
      continue;
    }
    const actual = await sha256(abs);
    if (actual !== entry.hash) {
      console.log(pc.yellow(`✗ drift: ${entry.path}`));
      console.log(pc.dim(`    manifest: ${entry.hash}`));
      console.log(pc.dim(`    actual:   ${actual}`));
      drift++;
    }
  }
  if (drift === 0 && missing === 0) {
    console.log(pc.green(`✓ all ${manifest.sources.length} source(s) match manifest`));
  } else {
    console.log(pc.red(`\n${drift} drift, ${missing} missing — run \`wiki source rehash <id|path>\` to refresh`));
    process.exitCode = 1;
  }
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
