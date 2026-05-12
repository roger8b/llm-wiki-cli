import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { today } from "../utils/misc.js";

const WIKI_SUBDIRS = [
  "concepts", "entities", "projects", "agents", "workflows", "decisions",
  "playbooks", "comparisons", "synthesis", "sources", "open-questions", "glossary",
];
const RAW_SUBDIRS = [
  "articles", "books", "documents", "transcripts", "specs", "images", "external",
];

export async function resetCmd(opts: { confirm?: boolean; yes?: boolean }) {
  const ctx = loadContext();

  if (!opts.confirm && !opts.yes) {
    console.log(pc.yellow("This will permanently delete:"));
    console.log("  • all raw sources under raw/");
    console.log("  • all pages under wiki/ (concepts, sources, decisions, …)");
    console.log("  • the source manifest");
    console.log("  • the log (reset to seed)");
    console.log("  • cache and reports");
    console.log();
    console.log(pc.dim("Preserved: schemas/, skills/, AGENTS.md, WIKI_PROTOCOL.md, wiki.config.yaml"));
    console.log();
    console.log(pc.red("Run again with --confirm to proceed."));
    return;
  }

  let removed = 0;

  // wipe wiki/<type>/*
  for (const sub of WIKI_SUBDIRS) {
    const dir = path.join(ctx.wikiDir, sub);
    if (fs.existsSync(dir)) {
      const files = await fs.readdir(dir);
      for (const f of files) {
        await fs.remove(path.join(dir, f));
        removed++;
      }
    } else {
      await fs.ensureDir(dir);
    }
  }

  // wipe raw/<type>/*
  for (const sub of RAW_SUBDIRS) {
    const dir = path.join(ctx.rawDir, sub);
    if (fs.existsSync(dir)) {
      const files = await fs.readdir(dir);
      for (const f of files) {
        await fs.remove(path.join(dir, f));
        removed++;
      }
    } else {
      await fs.ensureDir(dir);
    }
  }

  // reset manifest
  await fs.ensureDir(ctx.manifestsDir);
  await fs.writeJson(path.join(ctx.manifestsDir, "sources.json"), { sources: [] }, { spaces: 2 });

  // clear cache and reports
  for (const dir of [ctx.cacheDir, ctx.reportsDir, ctx.tempDir]) {
    if (fs.existsSync(dir)) {
      const files = await fs.readdir(dir);
      for (const f of files) await fs.remove(path.join(dir, f));
    } else {
      await fs.ensureDir(dir);
    }
  }

  // reset index.md
  await fs.writeFile(
    path.join(ctx.wikiDir, "index.md"),
    `# Wiki Index\n\nAuto-managed catalog. Rebuild with \`wiki index rebuild\`.\n`,
  );

  // reset log.md
  await fs.writeFile(
    path.join(ctx.wikiDir, "log.md"),
    `# Wiki Log\n\n## [${today()}] reset | brain reset to seed state\n- notes: all sources and pages removed via \`wiki reset\`\n`,
  );

  console.log(pc.green(`✓ brain reset — ${removed} file(s) removed`));

  // git commit if applicable
  if (fs.existsSync(path.join(ctx.root, ".git"))) {
    const { execa } = await import("execa");
    try {
      await execa("git", ["add", "-A"], { cwd: ctx.root });
      const { stdout } = await execa("git", ["status", "--porcelain"], { cwd: ctx.root });
      if (stdout.trim()) {
        await execa("git", ["commit", "-m", "reset: brain wiped to seed state"], { cwd: ctx.root });
        console.log(pc.green(`✓ git commit created`));
      }
    } catch (e: any) {
      console.log(pc.yellow(`! git commit skipped: ${e.shortMessage ?? e.message ?? e}`));
    }
  }
}
