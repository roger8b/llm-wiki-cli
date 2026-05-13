import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";

export async function doctorCmd() {
  const ctx = loadContext();
  const issues: string[] = [];
  const ok: string[] = [];

  for (const f of ctx.config.required_files) {
    const p = path.join(ctx.root, f);
    if (!fs.existsSync(p)) issues.push(`missing required file: ${f}`);
    else ok.push(`required file present: ${f}`);
  }

  for (const dir of [ctx.rawDir, ctx.wikiDir, ctx.schemasDir].concat(ctx.skillsDir ? [ctx.skillsDir] : [])) {
    if (!fs.existsSync(dir)) issues.push(`missing directory: ${path.relative(ctx.root, dir)}`);
    else ok.push(`dir ok: ${path.relative(ctx.root, dir)}`);
  }

  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  if (!fs.existsSync(manifestPath)) issues.push("missing manifest: .wiki/manifests/sources.json");

  console.log(pc.bold(`Wiki root: ${ctx.root}`));
  for (const m of ok) console.log(pc.green("  ✓ ") + m);
  for (const m of issues) console.log(pc.red("  ✗ ") + m);

  if (issues.length === 0) console.log(pc.green("\nAll checks passed."));
  else {
    console.log(pc.red(`\n${issues.length} issue(s) found.`));
    process.exitCode = 1;
  }
}
