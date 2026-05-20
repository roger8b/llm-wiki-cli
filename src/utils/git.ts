import path from "node:path";
import fs from "fs-extra";
import { execa } from "execa";
import type { WikiContext } from "./paths.js";

export function brainPaths(ctx: WikiContext): string[] {
  return [
    "wiki",
    "raw",
    "schemas",
    ctx.config.paths.skills ?? "skills",
    ".wiki/manifests",
    "wiki.config.yaml",
    "AGENTS.md",
    "WIKI_PROTOCOL.md",
  ];
}

export async function isGitRepo(root: string): Promise<boolean> {
  if (!fs.existsSync(path.join(root, ".git"))) return false;
  const r = await execa("git", ["rev-parse", "--is-inside-work-tree"], { cwd: root, reject: false });
  return r.exitCode === 0;
}

/**
 * Stage every brain-managed path that exists on disk. Returns true if anything was staged.
 * Never uses `git add -A` because the brain dir often contains user files (.obsidian, tmp).
 */
export async function stageBrainPaths(ctx: WikiContext): Promise<boolean> {
  for (const p of brainPaths(ctx)) {
    const abs = path.join(ctx.root, p);
    if (fs.existsSync(abs)) {
      await execa("git", ["add", "--", p], { cwd: ctx.root, reject: false });
    }
  }
  const { stdout } = await execa("git", ["diff", "--cached", "--name-only"], { cwd: ctx.root });
  return Boolean(stdout.trim());
}

export async function gitCommit(root: string, subject: string, body?: string): Promise<{ ok: boolean; err?: string }> {
  const args = ["commit", "-m", subject];
  if (body) args.push("-m", body);
  const r = await execa("git", args, { cwd: root, reject: false });
  if (r.exitCode !== 0) return { ok: false, err: r.stderr || r.stdout };
  return { ok: true };
}

export async function stagedFiles(root: string): Promise<string[]> {
  const r = await execa("git", ["diff", "--cached", "--name-only"], { cwd: root, reject: false });
  return r.stdout.trim().split("\n").filter(Boolean);
}
