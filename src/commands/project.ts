import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { checkbox, select } from "@inquirer/prompts";
import { templatesDir } from "../utils/templates-dir.js";
import { findWikiRoot } from "../utils/paths.js";
import { AGENTS, type AgentConfig, type AgentId, detectInstalledAgents } from "../utils/agents.js";

export interface ProjectInitOpts {
  wiki?: string;
  force?: boolean;
  yes?: boolean;
  scope?: "local" | "global" | "both";
  method?: "symlink" | "copy";
  showAll?: boolean;
  update?: boolean;
}

type Scope = "local" | "global" | "both";
type Method = "symlink" | "copy";
type ExistingAction = "keep" | "update" | "remove" | "ask-each";

// ── content generators ───────────────────────────────────────────────────────

const WIKI_SECTION_MARKER = "<!-- llm-wiki-start -->";
const WIKI_SECTION_END = "<!-- llm-wiki-end -->";

function boilerplate(wikiRoot: string, agentId: string): string {
  const def = AGENTS[agentId];
  const skillsDir = def?.skillsDir ?? ".agents/skills";
  const globalSkillsDir = def?.globalSkillsDir ?? "~/.wiki-cli/templates/skills";

  return `${WIKI_SECTION_MARKER}
# Brain (Global Knowledge Base)

The user maintains a persistent knowledge base — "the brain". You interact with it **only through the \`wiki\` CLI**. You never need to know where the brain lives on disk.

**Local Skills:**  \`${skillsDir}/wiki-*/SKILL.md\`
**Global Skills:** \`${globalSkillsDir}/wiki-*/SKILL.md\`

## Three hard rules

1. **Never read or write files inside the brain directly.** Every operation has a CLI command. If you don't know which, run \`wiki --help\`.
2. **Always maintain a todo list in working memory** when running a wiki workflow. **Never persist the todo list as a file.**
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
| Rebuild the index | \`wiki index rebuild\` |
| Append a log entry | \`wiki log add --type X --message "..."\` |
| Lint / check links / doctor | \`wiki lint\` / \`wiki links check\` / \`wiki doctor\` |

### Never invent commands

Commands not listed by \`wiki --help\` do not exist.

### Ingest is non-negotiable

When adding any file to the brain, follow the \`wiki-ingest\` skill:
1. \`wiki source add\` → registers and copies to the brain's raw store
2. \`wiki ingest prepare\` + \`wiki ingest context\` → get \`raw_path\` and \`source_hash\`
3. \`wiki page save\` / \`wiki page update\` → create source and concept pages
4. \`wiki ingest commit\` → validates and flips status to \`ingested\`

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
2. Decision pages with status \`canonical\` or \`reviewed\`
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

- All brain operations go through the \`wiki\` CLI. Run \`wiki --help\`.
- Files under \`${wikiRoot}/raw/\` are immutable.
- Load skills from \`.agents/skills/wiki-*/SKILL.md\` when triggers apply.
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

  if (existing.includes(WIKI_SECTION_MARKER)) {
    if (!force) return "skipped";
    const replaced = existing.replace(
      new RegExp(`${WIKI_SECTION_MARKER}[\\s\\S]*?${WIKI_SECTION_END}\\n?`, "m"),
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

// ── skills helpers ───────────────────────────────────────────────────────────

async function detectSkillsAt(dir: string): Promise<{ count: number; isSymlink: boolean }> {
  if (!fs.existsSync(dir)) return { count: 0, isSymlink: false };
  let count = 0;
  let isSymlink = false;
  try {
    const entries = await fs.readdir(dir);
    for (const e of entries) {
      const p = path.join(dir, e);
      if (e.startsWith("wiki-") && fs.existsSync(path.join(p, "SKILL.md"))) count++;
    }
    const wikiEntry = entries.find((e) => e.startsWith("wiki-"));
    if (wikiEntry) isSymlink = fs.lstatSync(path.join(dir, wikiEntry)).isSymbolicLink();
  } catch { /* ignore */ }
  return { count, isSymlink };
}

async function installSkills(
  destDir: string,
  srcDir: string,
  method: Method,
  force: boolean,
): Promise<number> {
  await fs.ensureDir(destDir);
  const entries = await fs.readdir(srcDir);
  let installed = 0;

  for (const e of entries) {
    const from = path.join(srcDir, e);
    const to = path.join(destDir, e);

    // `to` may be: missing, regular file/dir, valid symlink, or broken symlink.
    // existsSync follows symlinks (returns false on broken). lstatSync does
    // not follow but throws ENOENT when nothing is there. Detect via try/catch.
    let entryExists = false;
    try {
      fs.lstatSync(to);
      entryExists = true;
    } catch { /* truly absent */ }

    if (entryExists && !force) continue;

    if (entryExists) {
      try { await fs.remove(to); } catch { /* ignore */ }
    }

    if (method === "symlink") {
      try {
        await fs.ensureSymlink(from, to, "dir");
      } catch {
        // fallback to copy (e.g. Windows without symlink permission)
        await fs.copy(from, to, { overwrite: true });
      }
    } else {
      await fs.copy(from, to, { overwrite: true });
    }
    installed++;
  }

  return installed;
}

async function removeWikiSkills(dir: string): Promise<number> {
  if (!fs.existsSync(dir)) return 0;
  let removed = 0;
  const entries = await fs.readdir(dir);
  for (const e of entries) {
    if (!e.startsWith("wiki-")) continue;
    await fs.remove(path.join(dir, e));
    removed++;
  }
  return removed;
}

function resolveSkillsDestForAgent(target: string, def: AgentConfig, scope: Scope): string[] {
  const dests: string[] = [];
  if (scope === "local" || scope === "both") dests.push(path.join(target, def.skillsDir));
  if (scope === "global" || scope === "both") dests.push(def.globalSkillsDir);
  return dests;
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

  const detected = new Set(detectInstalledAgents());

  // Agents that already have wiki-* skills installed (local or global).
  // Used to pre-select checkbox items so users don't re-install accidentally.
  const alreadySetup = new Set<AgentId>();
  for (const [id, def] of Object.entries(AGENTS)) {
    const localCount = (await detectSkillsAt(path.join(target, def.skillsDir))).count;
    const globalCount = (await detectSkillsAt(def.globalSkillsDir)).count;
    if (localCount > 0 || globalCount > 0) alreadySetup.add(id);
  }

  // ── select agents ────────────────────────────────────────────────────────
  let selectedAgents: AgentId[];
  if (opts.yes) {
    if (alreadySetup.size > 0) selectedAgents = Array.from(alreadySetup);
    else if (detected.size > 0) selectedAgents = Array.from(detected);
    else selectedAgents = ["claude-code"];
  } else {
    const showAll = opts.showAll;
    const visible = Object.entries(AGENTS).filter(([id]) =>
      showAll || detected.has(id) || alreadySetup.has(id) || id === "claude-code"
    );

    selectedAgents = await checkbox({
      message: showAll
        ? `Agents (${Object.keys(AGENTS).length} total — use space to toggle)`
        : `Detected agents (${detected.size} found, ${alreadySetup.size} with wiki skills already set up)`,
      choices: visible.map(([id, def]) => {
        const tags: string[] = [];
        if (alreadySetup.has(id)) tags.push(pc.cyan("(wiki set up)"));
        else if (detected.has(id)) tags.push(pc.green("(detected)"));
        return {
          name: tags.length ? `${def.displayName} ${tags.join(" ")}` : def.displayName,
          value: id,
          checked: alreadySetup.has(id), // pre-select ONLY agents already configured
        };
      }),
    });
  }

  if (selectedAgents.length === 0) {
    console.log(pc.yellow("no agents selected — nothing to do."));
    return;
  }

  // ── scope ────────────────────────────────────────────────────────────────
  const scope: Scope = opts.scope ?? (
    opts.yes
      ? "local"
      : await select<Scope>({
          message: "Install skills where?",
          choices: [
            { name: "Local   (inside project, per agent dir)", value: "local" },
            { name: "Global  (in each agent's home dir)", value: "global" },
            { name: "Both    (local + global)", value: "both" },
          ],
        })
  );

  // ── method ───────────────────────────────────────────────────────────────
  const method: Method = opts.method ?? (
    opts.yes
      ? "symlink"
      : await select<Method>({
          message: "Skills installation method:",
          choices: [
            { name: "Symlink  (recommended — auto-updates when CLI updates skills)", value: "symlink" },
            { name: "Copy     (static snapshot)", value: "copy" },
          ],
        })
  );

  // ── compute unique skill destinations (dedup universal .agents/skills) ──
  const destToAgents = new Map<string, AgentId[]>();
  for (const id of selectedAgents) {
    const def = AGENTS[id];
    if (!def) continue;
    for (const dest of resolveSkillsDestForAgent(target, def, scope)) {
      const list = destToAgents.get(dest) ?? [];
      list.push(id);
      destToAgents.set(dest, list);
    }
  }

  // ── existing skills handling ─────────────────────────────────────────────
  const destsWithExisting: Array<{ dest: string; count: number; isSymlink: boolean }> = [];
  for (const dest of destToAgents.keys()) {
    const s = await detectSkillsAt(dest);
    if (s.count > 0) destsWithExisting.push({ dest, ...s });
  }

  let existingAction: ExistingAction = "update";
  if (destsWithExisting.length > 0 && !opts.update && !opts.force) {
    if (opts.yes) {
      existingAction = "update";
    } else {
      const total = destsWithExisting.reduce((s, d) => s + d.count, 0);
      existingAction = await select<ExistingAction>({
        message: `Found ${total} wiki skill(s) across ${destsWithExisting.length} location(s). Action?`,
        choices: [
          { name: "Update    (re-sync all from ~/.wiki-cli/templates/skills)", value: "update" },
          { name: "Keep      (don't touch existing)", value: "keep" },
          { name: "Remove    (wipe wiki-* then reinstall)", value: "remove" },
          { name: "Ask each  (prompt per location)", value: "ask-each" },
        ],
      });
    }
  } else if (opts.update) {
    existingAction = "update";
  }

  const td = templatesDir();
  const srcSkillsDir = path.join(td, "skills");
  if (!fs.existsSync(srcSkillsDir)) {
    console.error(pc.red(`skills templates not found at ${srcSkillsDir}. Reinstall the CLI.`));
    process.exitCode = 1;
    return;
  }

  // ── install skills per destination ───────────────────────────────────────
  console.log();
  for (const [dest, agentIds] of destToAgents) {
    const rel = path.relative(target, dest) || dest;
    const label = agentIds.length > 1
      ? `${rel} ${pc.dim(`(shared: ${agentIds.map((a) => AGENTS[a].displayName).join(", ")})`)}`
      : `${rel} ${pc.dim(`(${AGENTS[agentIds[0]].displayName})`)}`;

    console.log(pc.bold(label));

    let force = !!opts.force;
    let skipDest = false;

    const existing = destsWithExisting.find((d) => d.dest === dest);
    if (existing) {
      let action: ExistingAction = existingAction;
      if (action === "ask-each") {
        action = await select<ExistingAction>({
          message: `  ${rel}: ${existing.count} wiki skill(s) ${existing.isSymlink ? "(symlinked)" : "(copied)"}. Action?`,
          choices: [
            { name: "Update", value: "update" },
            { name: "Keep", value: "keep" },
            { name: "Remove", value: "remove" },
          ],
        });
      }
      if (action === "keep") {
        console.log(pc.dim(`  keeping ${existing.count} existing skill(s)`));
        skipDest = true;
      } else if (action === "remove") {
        const n = await removeWikiSkills(dest);
        console.log(pc.dim(`  removed ${n} wiki skill(s)`));
        force = true;
      } else if (action === "update") {
        force = true;
      }
    }

    if (!skipDest) {
      const n = await installSkills(dest, srcSkillsDir, method, force);
      const verb = method === "symlink" ? "symlinked" : "copied";
      console.log(pc.green(`  ✓ ${n} skill(s) ${verb}`));
    }
  }

  // ── rule files per agent ─────────────────────────────────────────────────
  console.log();
  const writtenRuleFiles = new Map<string, AgentId>();
  for (const agentId of selectedAgents) {
    const def = AGENTS[agentId];
    if (!def) continue;

    const ruleAbs = path.join(target, def.ruleFile);
    const content = def.ruleFormat === "cursor" ? cursorRule(wikiRoot) : boilerplate(wikiRoot, agentId);

    if (writtenRuleFiles.has(def.ruleFile)) {
      console.log(pc.dim(`  shared rule file already written: ${def.ruleFile} (${AGENTS[writtenRuleFiles.get(def.ruleFile)!].displayName})`));
      continue;
    }
    writtenRuleFiles.set(def.ruleFile, agentId);
    const result = await writeRuleFile(ruleAbs, content, def.appendOk, !!opts.force);
    const rel = path.relative(target, ruleAbs);
    if (result === "wrote") console.log(pc.green(`  ✓ wrote ${rel}`));
    else if (result === "appended") console.log(pc.green(`  ✚ appended to ${rel}`));
    else console.log(pc.yellow(`  skip (already has wiki section): ${rel}`));
  }

  // ── .llm-wiki.json ───────────────────────────────────────────────────────
  const configPath = path.join(target, ".llm-wiki.json");
  if (!fs.existsSync(configPath) || opts.force) {
    await fs.writeJson(
      configPath,
      {
        wiki_root: wikiRoot,
        agents: selectedAgents,
        scope,
        method,
        version: 2,
        installed_at: new Date().toISOString(),
      },
      { spaces: 2 },
    );
    console.log(pc.green(`\n✓ wrote .llm-wiki.json`));
  }

  console.log(pc.green(`\n✓ project wired to wiki. Run \`wiki doctor\` to verify.`));
}
