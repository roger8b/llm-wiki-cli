import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { today } from "../utils/misc.js";

export async function logAdd(opts: { type: string; message: string }) {
  const ctx = loadContext();
  const logPath = path.join(ctx.wikiDir, "log.md");
  const entry = `\n## [${today()}] ${opts.type} | ${opts.message}\n`;
  await fs.appendFile(logPath, entry);
  console.log(pc.green(`✓ appended log entry`));
}
