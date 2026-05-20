import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { execa } from "execa";
import { loadContext } from "../utils/paths.js";

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

async function git(args: string[], cwd: string) {
  return execa("git", args, { cwd, reject: false });
}

export async function commitCmd(opts: { message?: string; all?: boolean }) {
  const ctx = loadContext();
  const root = ctx.root;

  const inside = await git(["rev-parse", "--is-inside-work-tree"], root);
  if (inside.exitCode !== 0) {
    console.error(pc.red("not a git repo. Run `git init` in the brain root first."));
    process.exitCode = 1;
    return;
  }

  const status = await git(["status", "--porcelain"], root);
  if (!status.stdout.trim()) {
    console.log(pc.dim("nothing to commit"));
    return;
  }

  // stage brain-managed paths only (skip user-level files like .obsidian, tmp, etc.)
  const brainPaths = [
    "wiki",
    "raw",
    "schemas",
    ctx.config.paths.skills ?? "skills",
    ".wiki/manifests",
    "wiki.config.yaml",
    "AGENTS.md",
    "WIKI_PROTOCOL.md",
  ];
  for (const p of brainPaths) {
    const abs = path.join(root, p);
    if (fs.existsSync(abs)) {
      await git(["add", "--", p], root);
    }
  }

  const staged = await git(["diff", "--cached", "--name-only"], root);
  const stagedFiles = staged.stdout.trim().split("\n").filter(Boolean);
  if (stagedFiles.length === 0) {
    console.log(pc.dim("nothing brain-related to commit"));
    return;
  }

  // G1 guardrail: refuse if raw/ changed without matching log entry
  const rawChanged = stagedFiles.some((f) => f.startsWith("raw/"));
  const logChanged = stagedFiles.includes("wiki/log.md");
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
      if (entry) {
        message = `${entry.type}: ${entry.message}`;
      }
    }
  }
  if (!message) {
    message = "wiki: snapshot";
  }
  // keep subject under ~72 chars; split overflow into body
  let subject = message;
  let body = "";
  if (subject.length > 72) {
    subject = message.slice(0, 72).trimEnd();
    body = message;
  }

  const args = ["commit", "-m", subject];
  if (body) args.push("-m", body);
  const res = await git(args, root);
  if (res.exitCode !== 0) {
    console.error(pc.red("git commit failed:"));
    console.error(res.stderr || res.stdout);
    process.exitCode = 1;
    return;
  }
  console.log(pc.green("✓ committed"));
  console.log(pc.dim(`  files: ${stagedFiles.length}`));
  console.log(pc.dim(`  subject: ${subject}`));
}
