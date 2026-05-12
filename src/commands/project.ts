import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { checkbox, select, confirm } from "@inquirer/prompts";
import { templatesDir } from "../utils/templates-dir.js";
import { findWikiRoot } from "../utils/paths.js";

export interface ProjectInitOpts {
  wiki?: string;
  force?: boolean;
  yes?: boolean;
}

// ── agent definitions ────────────────────────────────────────────────────────

interface AgentDef {
  label: string;
  skillsDir?: string;          // relative to project root
  ruleFile: string;            // relative to project root
  ruleFormat: "boilerplate" | "cursor";
  appendOk: boolean;           // true = append to existing file, false = skip/overwrite
}

const AGENT_DEFS: Record<string, AgentDef> = {
  "claude-code": {
    label: "Claude Code",
    skillsDir: ".claude/skills",
    ruleFile: "CLAUDE.md",
    ruleFormat: "boilerplate",
    appendOk: true,
  },
  "pi": {
    label: "PI Agent",
    skillsDir: ".pi/skills",
    ruleFile: "AGENTS.md",
    ruleFormat: "boilerplate",
    appendOk: true,
  },
  "codex": {
    label: "Codex / OpenAI",
    ruleFile: "AGENTS.md",
    ruleFormat: "boilerplate",
    appendOk: true,
  },
  "gemini": {
    label: "Gemini CLI",
    ruleFile: "GEMINI.md",
    ruleFormat: "boilerplate",
    appendOk: true,
  },
  "cursor": {
    label: "Cursor",
    ruleFile: ".cursor/rules/llm-wiki.mdc",
    ruleFormat: "cursor",
    appendOk: false,
  },
  "amp": {
    label: "Amp",
    ruleFile: "AGENTS.md",
    ruleFormat: "boilerplate",
    appendOk: true,
  },
  "cline": {
    label: "Cline",
    ruleFile: ".clinerules",
    ruleFormat: "boilerplate",
    appendOk: true,
  },
};

// ── content generators ───────────────────────────────────────────────────────

const WIKI_SECTION_MARKER = "<!-- llm-wiki-start -->";
const WIKI_SECTION_END = "<!-- llm-wiki-end -->";

function boilerplate(wikiRoot: string, agentId: string): string {
  const def = AGENT_DEFS[agentId];
  const skillsNote = def?.skillsDir
    ? `- **Skills:** local copies live in \`${def.skillsDir}/\` (mirrored from the wiki).`
    : `- **Skills:** install with \`wiki init --skills-only\`.`;

  return `${WIKI_SECTION_MARKER}
# Global LLM Wiki integration

This project is wired to operate against the user's Global LLM Wiki.

- **Wiki root:** \`${wikiRoot}\`
- **Protocol:** read \`${wikiRoot}/WIKI_PROTOCOL.md\` before any persistent-knowledge task.
- **Index:** start navigation at \`${wikiRoot}/wiki/index.md\`.
${skillsNote}
- **CLI:** \`wiki\` — run \`wiki --help\` for commands.

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

Invoke them by name; the skills directory holds the SKILL.md files.

## Source priority

1. Current user instruction.
2. \`${wikiRoot}/wiki/decisions/\` with status \`canonical\` or \`reviewed\`.
3. Raw sources under \`${wikiRoot}/raw/\`.
4. Wiki pages with status \`canonical\`.
5. Wiki pages with status \`reviewed\`.
6. Wiki pages with status \`draft\`.
7. Agent inference, clearly labeled.
${WIKI_SECTION_END}
`;
}

function cursorRule(wikiRoot: string): string {
  return `---
description: Global LLM Wiki — treat as source of truth, follow protocol
alwaysApply: true
---

${WIKI_SECTION_MARKER}
This project is wired to the user's Global LLM Wiki at \`${wikiRoot}\`.

- Read \`${wikiRoot}/WIKI_PROTOCOL.md\` and \`${wikiRoot}/wiki/index.md\` before persistent-knowledge tasks.
- Files under \`${wikiRoot}/raw/\` are immutable.
- Use schemas from \`${wikiRoot}/schemas/\` when creating wiki pages.
- After updates, refresh \`wiki/index.md\` and append to \`wiki/log.md\`.
- Skills directory holds SKILL.md files.

CLI: \`wiki --help\`.
${WIKI_SECTION_END}
`;
}

// ── file helpers ─────────────────────────────────────────────────────────────

async function writeRuleFile(
  file: string,
  content: string,
  appendOk: boolean,
  force: boolean,
): Promise<"wrote" | "appended" | "skipped"> {
  await fs.ensureDir(path.dirname(file));

  if (!fs.existsSync(file)) {
    await fs.writeFile(file, content);
    return "wrote";
  }

  const existing = await fs.readFile(file, "utf8");

  // already has our section — refresh it if force, else skip
  if (existing.includes(WIKI_SECTION_MARKER)) {
    if (!force) return "skipped";
    const replaced = existing.replace(
      new RegExp(`${WIKI_SECTION_MARKER}[\\s\\S]*?${WIKI_SECTION_END}\n?`, "m"),
      content,
    );
    await fs.writeFile(file, replaced);
    return "wrote";
  }

  if (appendOk) {
    await fs.appendFile(file, "\n" + content);
    return "appended";
  }

  if (force) {
    await fs.writeFile(file, content);
    return "wrote";
  }

  return "skipped";
}

async function installSkills(
  skillsDir: string,
  srcSkillsDir: string,
  method: "copy" | "symlink",
  force: boolean,
): Promise<void> {
  await fs.ensureDir(skillsDir);
  const entries = await fs.readdir(srcSkillsDir);
  for (const e of entries) {
    const from = path.join(srcSkillsDir, e);
    const to = path.join(skillsDir, e);
    const populated = fs.existsSync(path.join(to, "SKILL.md")) ||
      (fs.existsSync(to) && fs.lstatSync(to).isSymbolicLink());
    if (populated && !force) {
      console.log(pc.yellow(`  skip skill (exists): ${path.relative(process.cwd(), to)}`));
      continue;
    }
    if (method === "symlink") {
      if (fs.existsSync(to)) await fs.remove(to);
      await fs.ensureSymlink(from, to, "dir");
      console.log(pc.green(`  ↔ skill symlinked: ${path.relative(process.cwd(), to)}`));
    } else {
      await fs.copy(from, to, { overwrite: true });
      console.log(pc.green(`  ✓ skill copied: ${path.relative(process.cwd(), to)}`));
    }
  }
}

// ── main command ─────────────────────────────────────────────────────────────

export async function projectInit(targetPath: string | undefined, opts: ProjectInitOpts) {
  const target = path.resolve(targetPath ?? ".");
  if (!fs.existsSync(target)) {
    console.error(pc.red(`target not found: ${target}`));
    process.exitCode = 1;
    return;
  }

  const wikiRoot = opts.wiki ? path.resolve(opts.wiki) : findWikiRoot(target) ?? findWikiRoot(process.cwd());
  if (!wikiRoot) {
    console.error(pc.red("wiki root not found. Pass --wiki <path> or set with: wiki config set-root <path>"));
    process.exitCode = 1;
    return;
  }

  console.log(pc.dim(`wiki root: ${wikiRoot}`));
  console.log(pc.dim(`project:   ${target}`));
  console.log();

  // ── interactive prompts ──────────────────────────────────────────────────

  const selectedAgents = opts.yes
    ? ["claude-code"]
    : await checkbox({
        message: "Which agents do you want to set up?",
        choices: Object.entries(AGENT_DEFS).map(([id, def]) => ({
          name: def.label,
          value: id,
          checked: id === "claude-code",
        })),
      });

  if (selectedAgents.length === 0) {
    console.log(pc.yellow("no agents selected — nothing to do."));
    return;
  }

  const skillMethod = opts.yes
    ? "copy"
    : await select({
        message: "Skills installation method:",
        choices: [
          { name: "Symlink  (recommended — auto-updates when wiki skills change)", value: "symlink" },
          { name: "Copy     (static snapshot, committed with project)", value: "copy" },
        ],
      });

  const force = !!opts.force;
  const td = templatesDir();
  const srcSkillsDir = path.join(td, "skills");

  console.log();

  // ── install per agent ────────────────────────────────────────────────────

  const ruleFiles = new Map<string, string>(); // file → agentId (dedupe shared files like AGENTS.md)

  for (const agentId of selectedAgents) {
    const def = AGENT_DEFS[agentId];
    console.log(pc.bold(`[${def.label}]`));

    // skills
    if (def.skillsDir) {
      const dest = path.join(target, def.skillsDir);
      await installSkills(dest, srcSkillsDir, skillMethod as "copy" | "symlink", force);
    }

    // rule file — dedupe: if multiple agents share AGENTS.md, only first one writes, rest append
    const ruleAbs = path.join(target, def.ruleFile);
    const content = def.ruleFormat === "cursor" ? cursorRule(wikiRoot) : boilerplate(wikiRoot, agentId);

    if (ruleFiles.has(def.ruleFile)) {
      // already written this turn by another agent — file now has our section, skip
      console.log(pc.dim(`  shared rule file already written: ${def.ruleFile}`));
    } else {
      ruleFiles.set(def.ruleFile, agentId);
      const result = await writeRuleFile(ruleAbs, content, def.appendOk, force);
      const rel = path.relative(target, ruleAbs);
      if (result === "wrote") console.log(pc.green(`  ✓ wrote ${rel}`));
      else if (result === "appended") console.log(pc.green(`  ✚ appended to ${rel}`));
      else console.log(pc.yellow(`  skip (already has wiki section): ${rel}`));
    }
  }

  // ── .llm-wiki.json ───────────────────────────────────────────────────────
  const configPath = path.join(target, ".llm-wiki.json");
  if (!fs.existsSync(configPath) || force) {
    await fs.writeJson(
      configPath,
      { wiki_root: wikiRoot, agents: selectedAgents, version: 1, installed_at: new Date().toISOString() },
      { spaces: 2 },
    );
    console.log(pc.green(`\n✓ wrote .llm-wiki.json`));
  }

  console.log(pc.green(`\n✓ project wired to wiki. Run \`wiki doctor\` to verify.`));
}
