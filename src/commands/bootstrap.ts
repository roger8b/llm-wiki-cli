import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { execa } from "execa";
import { templatesDir } from "../utils/templates-dir.js";
import { today } from "../utils/misc.js";
import { readGlobalConfig, writeGlobalConfig } from "../utils/global-config.js";

export interface BootstrapOpts {
  git?: boolean;
  force?: boolean;
  register?: boolean;
  noRegister?: boolean;
}

const WIKI_SUBDIRS = [
  "concepts","entities","projects","agents","workflows","decisions",
  "playbooks","comparisons","synthesis","sources","open-questions","glossary",
];
const RAW_SUBDIRS = [
  "articles","books","documents","transcripts","specs","images","external",
];

const GITIGNORE = `.wiki/cache/
.wiki/temp/
.wiki/reports/
.DS_Store
*.swp
node_modules/
`;

const INDEX_MD = `# Wiki Index

Auto-managed catalog. Rebuild with \`llm-wiki index rebuild\`.
`;

function logSeed(date: string): string {
  return `# Wiki Log

## [${date}] init | wiki bootstrap
- files: AGENTS.md, WIKI_PROTOCOL.md, wiki.config.yaml
- notes: initial scaffold created by llm-wiki init
`;
}

export async function bootstrapCmd(targetPath: string | undefined, opts: BootstrapOpts) {
  const target = path.resolve(targetPath ?? ".");
  const td = templatesDir();
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

  await fs.copy(path.join(td, "wiki.config.yaml"), configPath);
  await fs.copy(path.join(td, "AGENTS.md"), path.join(target, "AGENTS.md"));
  await fs.copy(path.join(td, "WIKI_PROTOCOL.md"), path.join(target, "WIKI_PROTOCOL.md"));
  await fs.writeFile(path.join(target, ".gitignore"), GITIGNORE);

  const indexPath = path.join(target, "wiki/index.md");
  if (!fs.existsSync(indexPath) || opts.force) await fs.writeFile(indexPath, INDEX_MD);
  const logPath = path.join(target, "wiki/log.md");
  if (!fs.existsSync(logPath) || opts.force) await fs.writeFile(logPath, logSeed(today()));

  await fs.copy(path.join(td, "schemas"), path.join(target, "schemas"), { overwrite: true });
  await fs.copy(path.join(td, "skills"), path.join(target, "skills"), { overwrite: true });

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

  const existing = readGlobalConfig();
  const shouldRegister = !opts.noRegister && (opts.register || !existing.wiki_root);
  if (shouldRegister) {
    await writeGlobalConfig({ ...existing, wiki_root: target });
    console.log(pc.green(`✓ registered as global wiki root (~/.llm-wiki/config.json)`));
  } else if (existing.wiki_root && existing.wiki_root !== target) {
    console.log(
      pc.yellow(
        `note: global wiki root is ${existing.wiki_root}. Pass --register to switch.`,
      ),
    );
  }

  console.log(pc.green(`✓ wiki bootstrapped at ${target}`));
}
