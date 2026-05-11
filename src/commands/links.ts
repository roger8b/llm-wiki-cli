import path from "node:path";
import fs from "fs-extra";
import fg from "fast-glob";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";

export async function linksCheck() {
  const ctx = loadContext();
  const files = await fg("**/*.md", { cwd: ctx.wikiDir, absolute: true });
  const re = /\[([^\]]+)\]\(([^)]+)\)/g;
  let broken = 0;
  for (const f of files) {
    const raw = await fs.readFile(f, "utf8");
    const dir = path.dirname(f);
    for (const m of raw.matchAll(re)) {
      const href = m[2].split("#")[0];
      if (!href || href.startsWith("http") || href.startsWith("mailto:")) continue;
      const target = path.resolve(dir, href);
      if (!fs.existsSync(target)) {
        console.log(pc.red(`broken `) + `${path.relative(ctx.root, f)} → ${href}`);
        broken++;
      }
    }
  }
  if (broken === 0) console.log(pc.green("✓ no broken links"));
  else {
    console.log(pc.red(`\n${broken} broken link(s)`));
    process.exitCode = 1;
  }
}
