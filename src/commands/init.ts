import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { execa } from "execa";
import {
  CONFIG_YAML,
  AGENTS_MD,
  PROTOCOL_MD,
  INDEX_MD,
  GITIGNORE,
  SCHEMAS,
  SKILLS,
  WIKI_SUBDIRS,
  RAW_SUBDIRS,
  logSeed,
} from "../templates/index.js";
import { today } from "../utils/misc.js";

export interface InitOpts {
  git?: boolean;
  force?: boolean;
}

export async function initCmd(targetPath: string | undefined, opts: InitOpts) {
  const target = path.resolve(targetPath ?? ".");
  await fs.ensureDir(target);

  const configPath = path.join(target, "wiki.config.yaml");
  if (fs.existsSync(configPath) && !opts.force) {
    console.log(pc.yellow(`wiki.config.yaml already exists at ${target}. Use --force to overwrite.`));
    return;
  }

  for (const sub of RAW_SUBDIRS) await fs.ensureDir(path.join(target, "raw", sub));
  for (const sub of WIKI_SUBDIRS) await fs.ensureDir(path.join(target, "wiki", sub));
  await fs.ensureDir(path.join(target, "schemas"));
  await fs.ensureDir(path.join(target, "skills"));
  await fs.ensureDir(path.join(target, ".wiki/cache"));
  await fs.ensureDir(path.join(target, ".wiki/manifests"));
  await fs.ensureDir(path.join(target, ".wiki/reports"));
  await fs.ensureDir(path.join(target, ".wiki/temp"));

  await fs.writeFile(configPath, CONFIG_YAML);
  await fs.writeFile(path.join(target, "AGENTS.md"), AGENTS_MD);
  await fs.writeFile(path.join(target, "WIKI_PROTOCOL.md"), PROTOCOL_MD);
  await fs.writeFile(path.join(target, ".gitignore"), GITIGNORE);

  const indexPath = path.join(target, "wiki/index.md");
  if (!fs.existsSync(indexPath) || opts.force) await fs.writeFile(indexPath, INDEX_MD);

  const logPath = path.join(target, "wiki/log.md");
  if (!fs.existsSync(logPath) || opts.force) await fs.writeFile(logPath, logSeed(today()));

  for (const [name, content] of Object.entries(SCHEMAS)) {
    await fs.writeFile(path.join(target, "schemas", name), content);
  }
  for (const [name, content] of Object.entries(SKILLS)) {
    await fs.writeFile(path.join(target, "skills", name), content);
  }

  const manifestPath = path.join(target, ".wiki/manifests/sources.json");
  if (!fs.existsSync(manifestPath)) {
    await fs.writeJson(manifestPath, { sources: [] }, { spaces: 2 });
  }

  if (opts.git && !fs.existsSync(path.join(target, ".git"))) {
    try {
      await execa("git", ["init"], { cwd: target });
      console.log(pc.green(`git initialized at ${target}`));
    } catch (e: any) {
      console.log(pc.yellow(`git init skipped: ${e.message}`));
    }
  }

  console.log(pc.green(`✓ wiki initialized at ${target}`));
}
