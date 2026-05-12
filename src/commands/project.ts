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
  const skillsDir = def?.skillsDir ?? ".claude/skills";

  return `${WIKI_SECTION_MARKER}
# Brain (Global Knowledge Base)

**Brain root:** \`${wikiRoot}\`
**CLI binary:** \`wiki\` (run \`wiki --help\` for the full command list — never invent commands)
**Skills:** \`${skillsDir}/wiki-*/SKILL.md\`

## Hard rules

### WRITES always go through the CLI

Never create, edit, or write any file under \`${wikiRoot}/\` directly.
Every write operation has a CLI command — use it:

| Operation | Command |
|-----------|---------|
| Register a source | \`wiki source add <file> --type <type>\` |
| Prepare ingest context | \`wiki ingest prepare raw/<type>/<file>\` |
| Commit after agent creates pages | \`wiki ingest commit raw/<type>/<file>\` |
| Rebuild index | \`wiki index rebuild\` |
| Append to log | \`wiki log add --type ingest --message "..."\` |
| Create a new page stub | \`wiki page new <type> <title>\` |

If you are unsure whether a command exists, run \`wiki --help\` first. Do not guess.

### READS can be direct

Reading files is fine without CLI: schemas, wiki pages, WIKI_PROTOCOL.md, index.md.
Use read, cat, or grep freely to understand content.

### Ingest workflow is non-negotiable

When adding any file to the brain:
1. \`wiki source add <absolute-path> --type <type>\` — registers in manifest, copies to \`raw/\`
2. \`wiki ingest prepare raw/<type>/<file>\` — generates \`.wiki/cache/ingest-context.md\`
3. Agent reads ingest context and creates wiki pages (use \`raw_path\` and \`source_hash\` from context)
4. \`wiki ingest commit raw/<type>/<file>\` — validates and flips status to \`ingested\`

Skipping steps 1–2 leaves the source orphaned — invisible to \`wiki source list\`, \`wiki lint\`, and \`wiki ingest commit\`.

### Never hallucinate CLI commands

Commands like \`wiki index show\`, \`wiki schema show\`, \`wiki source read\` do not exist.
When uncertain, run \`wiki --help\` and use only commands listed there.

## Available skills

| Skill | When to use |
|-------|-------------|
| \`wiki-ingest\` | Adding any file or document to the brain |
| \`wiki-query\` | Answering a question grounded in brain content |
| \`wiki-source-of-truth\` | Any task requiring knowledge from the brain |
| \`wiki-lint\` | Auditing brain health |
| \`wiki-refactor\` | Merging, splitting, or restructuring pages |
| \`wiki-decision-capture\` | Persisting decisions made in conversation |

## Source priority

1. User's current instruction
2. \`${wikiRoot}/wiki/decisions/\` — status \`canonical\` or \`reviewed\`
3. \`${wikiRoot}/raw/\` — immutable source files (read only, never modify)
4. Wiki pages — \`canonical\` > \`reviewed\` > \`draft\`
5. Agent inference — clearly labeled as such
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
