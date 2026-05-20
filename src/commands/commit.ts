import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { gitCommit, isGitRepo, stageBrainPaths, stagedFiles } from "../utils/git.js";

interface LogEntry {
  date: string;
  type: string;
  message: string;
}

function parseLastLogEntry(content: string): LogEntry | undefined {
  const re = /^## \[(\d{4}-\d{2}-\d{2})\]\s+(\S+)\s*\|\s*(.+)$/gm;
  let last: LogEntry | undefined;
  for (const m of content.matchAll(re)) {
    last = { date: m[1], type: m[2], message: m[3].trim() };
  }
  return last;
}

export async function commitCmd(opts: { message?: string }) {
  const ctx = loadContext();
  const root = ctx.root;

  if (!(await isGitRepo(root))) {
    console.error(pc.red("not a git repo. Run `git init` in the brain root first."));
    process.exitCode = 1;
    return;
  }

  const staged = await stageBrainPaths(ctx);
  if (!staged) {
    console.log(pc.dim("nothing brain-related to commit"));
    return;
  }
  const files = await stagedFiles(root);

  // G1 guardrail: refuse if raw/ changed without matching log entry
  const rawChanged = files.some((f) => f.startsWith("raw/"));
  const logChanged = files.includes("wiki/log.md");
  if (rawChanged && !logChanged && ctx.config.source_policy?.require_log_entry_for_updates) {
    console.error(pc.red("raw/ changed but wiki/log.md is not staged."));
    console.error(pc.dim("add a log entry first: `wiki log add --type <op> --message <m>`"));
    process.exitCode = 1;
    return;
  }

  let message = opts.message;
  if (!message) {
    const logPath = path.join(ctx.wikiDir, "log.md");
    if (fs.existsSync(logPath)) {
      const entry = parseLastLogEntry(await fs.readFile(logPath, "utf8"));
      if (entry) message = `${entry.type}: ${entry.message}`;
    }
  }
  if (!message) message = "wiki: snapshot";

  let subject = message;
  let body = "";
  if (subject.length > 72) {
    subject = message.slice(0, 72).trimEnd();
    body = message;
  }

  const res = await gitCommit(root, subject, body || undefined);
  if (!res.ok) {
    console.error(pc.red("git commit failed:"));
    console.error(res.err);
    process.exitCode = 1;
    return;
  }
  console.log(pc.green("✓ committed"));
  console.log(pc.dim(`  files: ${files.length}`));
  console.log(pc.dim(`  subject: ${subject}`));
}
