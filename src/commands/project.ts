import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { templatesDir } from "../utils/templates-dir.js";
import { findWikiRoot } from "../utils/paths.js";

export interface ProjectInitOpts {
  wiki?: string;
  skills?: boolean;
  agents?: boolean;
  claude?: boolean;
  gemini?: boolean;
  cursor?: boolean;
  force?: boolean;
}

function boilerplate(wikiRoot: string): string {
  return `# Global LLM Wiki integration

This project is wired to operate against the user's Global LLM Wiki.

- **Wiki root:** \`${wikiRoot}\`
- **Protocol:** read \`${wikiRoot}/WIKI_PROTOCOL.md\` before any persistent-knowledge task.
- **Index:** start navigation at \`${wikiRoot}/wiki/index.md\`.
- **Skills:** local copies live in \`.claude/skills/\` (mirrored from the wiki).
- **CLI:** \`llm-wiki\` — run \`llm-wiki --help\` for commands.

## Mandatory rules for agents in this repo

1. Persistent knowledge belongs in the wiki, not in chat history.
2. Files under \`${wikiRoot}/raw/\` are immutable. Read, never modify.
3. When creating or updating wiki pages, use the proper schema from \`${wikiRoot}/schemas/\` and add valid frontmatter.
4. After any change to the wiki, update \`${wikiRoot}/wiki/index.md\` and append to \`${wikiRoot}/wiki/log.md\`.
5. If new information conflicts with existing pages, flag the contradiction — never silently overwrite.
6. Durable conclusions go under \`${wikiRoot}/wiki/synthesis/\`, \`comparisons/\`, \`playbooks/\`, \`decisions/\`, or \`open-questions/\`.

## Available wiki skills

- \`wiki-source-of-truth\` — treat the wiki as the canonical knowledge base.
- \`wiki-ingest\` — incorporate a new raw source.
- \`wiki-query\` — answer a question grounded in the wiki, save durable conclusions.
- \`wiki-lint\` — audit wiki health.
- \`wiki-refactor\` — restructure without losing knowledge.
- \`wiki-decision-capture\` — persist decisions made during conversation.

Invoke them by name; the \`.claude/skills/\` directory holds the SKILL.md files.

## Source priority

1. Current user instruction.
2. \`${wikiRoot}/wiki/decisions/\` with status \`canonical\` or \`reviewed\`.
3. Raw sources under \`${wikiRoot}/raw/\`.
4. Wiki pages with status \`canonical\`.
5. Wiki pages with status \`reviewed\`.
6. Wiki pages with status \`draft\`.
7. Agent inference, clearly labeled.
`;
}

function cursorRule(wikiRoot: string): string {
  return `---
description: Global LLM Wiki — treat as source of truth, follow protocol
alwaysApply: true
---

This project is wired to the user's Global LLM Wiki at \`${wikiRoot}\`.

- Read \`${wikiRoot}/WIKI_PROTOCOL.md\` and \`${wikiRoot}/wiki/index.md\` before persistent-knowledge tasks.
- Files under \`${wikiRoot}/raw/\` are immutable.
- Use schemas from \`${wikiRoot}/schemas/\` when creating wiki pages.
- After updates, refresh \`wiki/index.md\` and append to \`wiki/log.md\`.
- Skills live in \`.claude/skills/\`.

CLI: \`llm-wiki --help\`.
`;
}

async function writeIfAllowed(file: string, content: string, force: boolean): Promise<boolean> {
  if (fs.existsSync(file) && !force) {
    console.log(pc.yellow(`skip (exists): ${file}`));
    return false;
  }
  await fs.ensureDir(path.dirname(file));
  await fs.writeFile(file, content);
  console.log(pc.green(`✓ wrote ${file}`));
  return true;
}

export async function projectInit(targetPath: string | undefined, opts: ProjectInitOpts) {
  const target = path.resolve(targetPath ?? ".");
  if (!fs.existsSync(target)) {
    console.error(pc.red(`target not found: ${target}`));
    process.exitCode = 1;
    return;
  }
  const td = templatesDir();

  let wikiRoot = opts.wiki ? path.resolve(opts.wiki) : findWikiRoot(target) ?? findWikiRoot(process.cwd());
  if (!wikiRoot) {
    console.error(
      pc.red(
        "wiki root not found. Pass --wiki <path> or cd into a project that lives near the wiki.",
      ),
    );
    process.exitCode = 1;
    return;
  }
  console.log(pc.dim(`wiki root: ${wikiRoot}`));
  console.log(pc.dim(`target:    ${target}`));

  const all = opts.skills === undefined && opts.agents === undefined && opts.claude === undefined && opts.gemini === undefined && opts.cursor === undefined;
  const want = {
    skills: all || opts.skills,
    agents: all || opts.agents,
    claude: all || opts.claude,
    gemini: all || opts.gemini,
    cursor: all || opts.cursor,
  };

  const body = boilerplate(wikiRoot);
  const force = !!opts.force;

  if (want.skills) {
    const dest = path.join(target, ".claude/skills");
    await fs.ensureDir(dest);
    const srcSkills = path.join(td, "skills");
    const entries = await fs.readdir(srcSkills);
    for (const e of entries) {
      const from = path.join(srcSkills, e);
      const to = path.join(dest, e);
      if (fs.existsSync(to) && !force) {
        console.log(pc.yellow(`skip skill (exists): .claude/skills/${e}`));
        continue;
      }
      await fs.copy(from, to, { overwrite: force });
      console.log(pc.green(`✓ skill installed: .claude/skills/${e}`));
    }
  }

  if (want.agents) await writeIfAllowed(path.join(target, "AGENTS.md"), body, force);
  if (want.claude) await writeIfAllowed(path.join(target, "CLAUDE.md"), body, force);
  if (want.gemini) await writeIfAllowed(path.join(target, "GEMINI.md"), body, force);
  if (want.cursor) {
    await writeIfAllowed(
      path.join(target, ".cursor/rules/llm-wiki.mdc"),
      cursorRule(wikiRoot),
      force,
    );
  }

  const configPath = path.join(target, ".llm-wiki.json");
  if (!fs.existsSync(configPath) || force) {
    await fs.writeJson(
      configPath,
      { wiki_root: wikiRoot, version: 1, installed_at: new Date().toISOString() },
      { spaces: 2 },
    );
    console.log(pc.green(`✓ wrote .llm-wiki.json`));
  }

  console.log(pc.green(`\n✓ project ready. Skills available under .claude/skills/.`));
  console.log(pc.dim(`  Use --force to overwrite existing files.`));
}
