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

The user maintains a persistent knowledge base — "the brain". You interact with it **only through the \`wiki\` CLI**. You never need to know where the brain lives on disk.

**Skills:** \`${skillsDir}/wiki-*/SKILL.md\` — load them when their triggers apply.

## Three hard rules

1. **Never read or write files inside the brain directly.** Every operation has a CLI command. If you don't know which, run \`wiki --help\`.
2. **Always maintain a todo list in working memory** when running a wiki workflow (use TodoWrite or your platform's in-memory todo tool). **Never persist the todo list as a file.** Multi-step wiki workflows lose track without one.
3. **Compose page content in memory and pipe via stdin (heredoc).** **Never write a temp file under \`/tmp/\`** to pass content to \`wiki page save\` / \`wiki page update\`.

| To … | Use … |
|------|-------|
| Read the brain protocol | \`wiki protocol\` |
| See the index | \`wiki index show\` |
| List schemas / read a schema | \`wiki schema list\` / \`wiki schema show <type>\` |
| List pages / read a page | \`wiki page list [--type X] [--status Y]\` / \`wiki page show <slug>\` |
| Search across pages | \`wiki search "<query>"\` |
| Read recent log | \`wiki log show --last 10\` |
| Read a raw source | \`wiki source show <id-or-name>\` |
| Register a new source | \`wiki source add <file> --type <type>\` |
| Prepare ingest context | \`wiki ingest prepare <raw-path>\` |
| Read ingest context | \`wiki ingest context\` |
| Commit an ingest | \`wiki ingest commit <raw-path>\` |
| Save a new page (stdin) | \`cat <<'EOF' \| wiki page save --type X --title "Y" ... EOF\` |
| Update an existing page (stdin) | \`cat <<'EOF' \| wiki page update <bare-slug> ... EOF\` |
| Save a query answer (stdin) | \`cat <<'EOF' \| wiki page save --type synthesis --title "Y" ... EOF\` |
| Rebuild the index | \`wiki index rebuild\` |
| Append a log entry | \`wiki log add --type X --message "..."\` |
| Lint / check links / doctor | \`wiki lint\` / \`wiki links check\` / \`wiki doctor\` |

When you need to write page content, generate the content in a temp file under \`/tmp/\` and pass it via \`--file\`, or pipe via stdin. Never write inside the brain.

### Never invent commands

Commands not listed by \`wiki --help\` do not exist. If unsure, run \`wiki --help\` and use only what is there.

### Ingest is non-negotiable

When adding any file to the brain, follow the \`wiki-ingest\` skill:
1. \`wiki source add\` → registers and copies to the brain's raw store
2. \`wiki ingest prepare\` + \`wiki ingest context\` → get the \`raw_path\` and \`source_hash\` to use
3. \`wiki page save\` / \`wiki page update\` → create source and concept pages
4. \`wiki ingest commit\` → validates and flips status to \`ingested\`

Skipping the CLI leaves the source orphaned, invisible to \`wiki source list\` / \`wiki lint\` / \`wiki ingest commit\`.

## Available skills

| Skill | When to load |
|-------|--------------|
| \`wiki-ingest\` | Adding any file or document to the brain |
| \`wiki-query\` | Answering a question grounded in brain content |
| \`wiki-source-of-truth\` | Any task that should be grounded in the brain |
| \`wiki-lint\` | Auditing brain health |
| \`wiki-refactor\` | Merging, splitting, deprecating, or renaming pages |
| \`wiki-decision-capture\` | Persisting a decision the user made in conversation |

## Source priority

1. User's current instruction
2. Decision pages with status \`canonical\` or \`reviewed\` (\`wiki page list --type decision --status canonical\`)
3. Raw sources (\`wiki source show <id>\`)
4. Other pages by status: \`canonical\` > \`reviewed\` > \`draft\`
5. Your own inference, clearly labeled
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
