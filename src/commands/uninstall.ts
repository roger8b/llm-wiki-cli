import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import { checkbox, select, confirm } from "@inquirer/prompts";
import { AGENTS, type AgentId } from "../utils/agents.js";

export interface UninstallOpts {
  scope?: "local" | "global" | "both";
  yes?: boolean;
  force?: boolean;
}

type Scope = "local" | "global" | "both";

const WIKI_SECTION_MARKER = "<!-- llm-wiki-start -->";
const WIKI_SECTION_END = "<!-- llm-wiki-end -->";

async function removeWikiSkills(dir: string): Promise<number> {
  if (!fs.existsSync(dir)) return 0;
  let removed = 0;
  const entries = await fs.readdir(dir);
  for (const e of entries) {
    if (!e.startsWith("wiki-")) continue;
    await fs.remove(path.join(dir, e));
    removed++;
  }
  // remove dir if empty
  try {
    const remaining = await fs.readdir(dir);
    if (remaining.length === 0) await fs.remove(dir);
  } catch { /* ignore */ }
  return removed;
}

async function hasWikiSkills(dir: string): Promise<number> {
  if (!fs.existsSync(dir)) return 0;
  try {
    const entries = await fs.readdir(dir);
    return entries.filter((e) => e.startsWith("wiki-") && fs.existsSync(path.join(dir, e, "SKILL.md"))).length;
  } catch { return 0; }
}

export async function projectUninstall(targetPath: string | undefined, opts: UninstallOpts) {
  const target = path.resolve(targetPath ?? ".");
  if (!fs.existsSync(target)) {
    console.error(pc.red(`target not found: ${target}`));
    process.exitCode = 1;
    return;
  }

  console.log(pc.dim(`project: ${target}`));
  console.log();

  // Load .llm-wiki.json
  const configPath = path.join(target, ".llm-wiki.json");
  let knownAgents: AgentId[] = [];
  if (fs.existsSync(configPath)) {
    try {
      const cfg = fs.readJsonSync(configPath) as { agents?: string[] };
      knownAgents = cfg.agents ?? [];
    } catch { /* ignore */ }
  }

  // Detect agents that actually have wiki-* skills installed (local or global)
  type Row = { id: AgentId; localCount: number; globalCount: number };
  const rows: Row[] = [];

  const candidates: AgentId[] = knownAgents.length > 0
    ? Array.from(new Set([...knownAgents, ...Object.keys(AGENTS)]))
    : Object.keys(AGENTS);

  for (const id of candidates) {
    const def = AGENTS[id];
    if (!def) continue;
    const localDir = path.join(target, def.skillsDir);
    const globalDir = def.globalSkillsDir;
    const localCount = await hasWikiSkills(localDir);
    const globalCount = await hasWikiSkills(globalDir);
    if (localCount > 0 || globalCount > 0) {
      rows.push({ id, localCount, globalCount });
    }
  }

  if (rows.length === 0) {
    console.log(pc.yellow("no wiki skills found in project or global agent dirs."));
    return;
  }

  // ── select agents ────────────────────────────────────────────────────────
  const selected = opts.yes
    ? rows.map((r) => r.id)
    : await checkbox({
        message: "Which agents to uninstall?",
        choices: rows.map(({ id, localCount, globalCount }) => {
          const parts = [
            localCount > 0 ? `local: ${localCount}` : null,
            globalCount > 0 ? `global: ${globalCount}` : null,
          ].filter(Boolean).join(", ");
          return {
            name: `${AGENTS[id].displayName} ${pc.dim(`(${parts})`)}`,
            value: id,
            checked: false,
          };
        }),
      });

  if (selected.length === 0) {
    console.log(pc.yellow("no agents selected — nothing to do."));
    return;
  }

  // ── scope ────────────────────────────────────────────────────────────────
  const scope: Scope = opts.scope ?? (
    opts.yes
      ? "local"
      : await select<Scope>({
          message: "Remove from where?",
          choices: [
            { name: "Local   (project dirs only)", value: "local" },
            { name: "Global  (agent home dirs only)", value: "global" },
            { name: "Both    (local + global)", value: "both" },
          ],
        })
  );

  if (!opts.yes && !opts.force) {
    const ok = await confirm({
      message: `Remove wiki skills for ${selected.length} agent(s) from ${scope}?`,
      default: false,
    });
    if (!ok) { console.log(pc.dim("cancelled.")); return; }
  }

  // ── uninstall ────────────────────────────────────────────────────────────
  console.log();
  // dedup destinations (universal .agents/skills shared)
  const dests = new Set<string>();
  for (const id of selected) {
    const def = AGENTS[id];
    if (scope === "local" || scope === "both") dests.add(path.join(target, def.skillsDir));
    if (scope === "global" || scope === "both") dests.add(def.globalSkillsDir);
  }

  let total = 0;
  for (const dest of dests) {
    const n = await removeWikiSkills(dest);
    if (n > 0) {
      console.log(pc.green(`  ✓ removed ${n} skill(s) from ${dest}`));
      total += n;
    }
  }

  // ── clean rule files (only per-agent files; AGENTS.md only if no other agent still uses it) ──
  const stillUsingAgentsMd = Object.entries(AGENTS).some(
    ([id, def]) => def.ruleFile === "AGENTS.md" && knownAgents.includes(id) && !selected.includes(id),
  );

  const cleanedFiles = new Set<string>();
  for (const id of selected) {
    const def = AGENTS[id];
    const ruleAbs = path.join(target, def.ruleFile);
    if (cleanedFiles.has(ruleAbs)) continue;
    if (def.ruleFile === "AGENTS.md" && stillUsingAgentsMd) continue;
    if (!fs.existsSync(ruleAbs)) continue;

    const content = await fs.readFile(ruleAbs, "utf8");
    if (!content.includes(WIKI_SECTION_MARKER)) continue;

    const cleaned = content
      .replace(new RegExp(`${WIKI_SECTION_MARKER}[\\s\\S]*?${WIKI_SECTION_END}\\n?`, "m"), "")
      .trim();

    if (cleaned.length === 0) {
      await fs.remove(ruleAbs);
      console.log(pc.dim(`  removed empty ${path.relative(target, ruleAbs)}`));
    } else {
      await fs.writeFile(ruleAbs, cleaned + "\n");
      console.log(pc.dim(`  cleaned ${path.relative(target, ruleAbs)}`));
    }
    cleanedFiles.add(ruleAbs);
  }

  // ── update .llm-wiki.json ────────────────────────────────────────────────
  if (fs.existsSync(configPath)) {
    try {
      const cfg = fs.readJsonSync(configPath) as Record<string, unknown>;
      const remaining = (knownAgents).filter((a) => !selected.includes(a));
      cfg.agents = remaining;
      cfg.uninstalled_at = new Date().toISOString();
      await fs.writeJson(configPath, cfg, { spaces: 2 });
    } catch { /* ignore */ }
  }

  console.log(pc.green(`\n✓ uninstalled wiki skills for ${selected.length} agent(s) (${total} total)`));
}
