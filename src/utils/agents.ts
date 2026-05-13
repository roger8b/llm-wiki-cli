import os from "node:os";
import path from "node:path";
import fs from "fs-extra";

// Mirror of https://github.com/vercel-labs/skills/blob/main/src/agents.ts
// extended with rule-file metadata (ruleFile, ruleFormat, appendOk) used by
// the wiki CLI to wire AGENTS.md / CLAUDE.md / GEMINI.md / etc.

const home = os.homedir();
const configHome = process.env.XDG_CONFIG_HOME ?? path.join(home, ".config");
const codexHome = process.env.CODEX_HOME ?? path.join(home, ".codex");
const claudeHome = process.env.CLAUDE_CONFIG_DIR ?? path.join(home, ".claude");
const vibeHome = process.env.VIBE_HOME ?? path.join(home, ".vibe");

export type AgentId = string;

export interface AgentConfig {
  name: AgentId;
  displayName: string;
  skillsDir: string;          // relative to project (workspace install)
  globalSkillsDir: string;    // absolute (global install)
  ruleFile: string;           // relative to project
  ruleFormat: "boilerplate" | "cursor";
  appendOk: boolean;          // append wiki section to existing rule file?
  showInUniversalList?: boolean;
  detectInstalled: () => boolean;
}

function openClawGlobal(): string {
  if (fs.existsSync(path.join(home, ".openclaw")))  return path.join(home, ".openclaw/skills");
  if (fs.existsSync(path.join(home, ".clawdbot"))) return path.join(home, ".clawdbot/skills");
  if (fs.existsSync(path.join(home, ".moltbot")))  return path.join(home, ".moltbot/skills");
  return path.join(home, ".openclaw/skills");
}

export const AGENTS: Record<AgentId, AgentConfig> = {
  "aider-desk": {
    name: "aider-desk", displayName: "AiderDesk",
    skillsDir: ".aider-desk/skills",
    globalSkillsDir: path.join(home, ".aider-desk/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".aider-desk")),
  },
  amp: {
    name: "amp", displayName: "Amp",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(configHome, "agents/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(configHome, "amp")),
  },
  antigravity: {
    name: "antigravity", displayName: "Antigravity",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".gemini/antigravity/skills"),
    ruleFile: "GEMINI.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".gemini/antigravity")),
  },
  augment: {
    name: "augment", displayName: "Augment",
    skillsDir: ".augment/skills",
    globalSkillsDir: path.join(home, ".augment/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".augment")),
  },
  bob: {
    name: "bob", displayName: "IBM Bob",
    skillsDir: ".bob/skills",
    globalSkillsDir: path.join(home, ".bob/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".bob")),
  },
  "claude-code": {
    name: "claude-code", displayName: "Claude Code",
    skillsDir: ".claude/skills",
    globalSkillsDir: path.join(claudeHome, "skills"),
    ruleFile: "CLAUDE.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(claudeHome),
  },
  openclaw: {
    name: "openclaw", displayName: "OpenClaw",
    skillsDir: "skills",
    globalSkillsDir: openClawGlobal(),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () =>
      fs.existsSync(path.join(home, ".openclaw")) ||
      fs.existsSync(path.join(home, ".clawdbot")) ||
      fs.existsSync(path.join(home, ".moltbot")),
  },
  cline: {
    name: "cline", displayName: "Cline",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".agents/skills"),
    ruleFile: ".clinerules", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".cline")),
  },
  "codearts-agent": {
    name: "codearts-agent", displayName: "CodeArts Agent",
    skillsDir: ".codeartsdoer/skills",
    globalSkillsDir: path.join(home, ".codeartsdoer/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".codeartsdoer")),
  },
  codebuddy: {
    name: "codebuddy", displayName: "CodeBuddy",
    skillsDir: ".codebuddy/skills",
    globalSkillsDir: path.join(home, ".codebuddy/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () =>
      fs.existsSync(path.join(process.cwd(), ".codebuddy")) || fs.existsSync(path.join(home, ".codebuddy")),
  },
  codemaker: {
    name: "codemaker", displayName: "Codemaker",
    skillsDir: ".codemaker/skills",
    globalSkillsDir: path.join(home, ".codemaker/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".codemaker")),
  },
  codestudio: {
    name: "codestudio", displayName: "Code Studio",
    skillsDir: ".codestudio/skills",
    globalSkillsDir: path.join(home, ".codestudio/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".codestudio")),
  },
  codex: {
    name: "codex", displayName: "Codex",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(codexHome, "skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(codexHome) || fs.existsSync("/etc/codex"),
  },
  "command-code": {
    name: "command-code", displayName: "Command Code",
    skillsDir: ".commandcode/skills",
    globalSkillsDir: path.join(home, ".commandcode/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".commandcode")),
  },
  continue: {
    name: "continue", displayName: "Continue",
    skillsDir: ".continue/skills",
    globalSkillsDir: path.join(home, ".continue/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () =>
      fs.existsSync(path.join(process.cwd(), ".continue")) || fs.existsSync(path.join(home, ".continue")),
  },
  cortex: {
    name: "cortex", displayName: "Cortex Code",
    skillsDir: ".cortex/skills",
    globalSkillsDir: path.join(home, ".snowflake/cortex/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".snowflake/cortex")),
  },
  crush: {
    name: "crush", displayName: "Crush",
    skillsDir: ".crush/skills",
    globalSkillsDir: path.join(home, ".config/crush/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".config/crush")),
  },
  cursor: {
    name: "cursor", displayName: "Cursor",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".cursor/skills"),
    ruleFile: ".cursor/rules/llm-wiki.mdc", ruleFormat: "cursor", appendOk: false,
    detectInstalled: () => fs.existsSync(path.join(home, ".cursor")),
  },
  deepagents: {
    name: "deepagents", displayName: "Deep Agents",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".deepagents/agent/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".deepagents")),
  },
  devin: {
    name: "devin", displayName: "Devin for Terminal",
    skillsDir: ".devin/skills",
    globalSkillsDir: path.join(configHome, "devin/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(configHome, "devin")),
  },
  dexto: {
    name: "dexto", displayName: "Dexto",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".agents/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".dexto")),
  },
  droid: {
    name: "droid", displayName: "Droid",
    skillsDir: ".factory/skills",
    globalSkillsDir: path.join(home, ".factory/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".factory")),
  },
  firebender: {
    name: "firebender", displayName: "Firebender",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".firebender/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".firebender")),
  },
  forgecode: {
    name: "forgecode", displayName: "ForgeCode",
    skillsDir: ".forge/skills",
    globalSkillsDir: path.join(home, ".forge/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".forge")),
  },
  "gemini-cli": {
    name: "gemini-cli", displayName: "Gemini CLI",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".gemini/skills"),
    ruleFile: "GEMINI.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".gemini")),
  },
  "github-copilot": {
    name: "github-copilot", displayName: "GitHub Copilot",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".copilot/skills"),
    ruleFile: ".github/copilot-instructions.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".copilot")),
  },
  goose: {
    name: "goose", displayName: "Goose",
    skillsDir: ".goose/skills",
    globalSkillsDir: path.join(configHome, "goose/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(configHome, "goose")),
  },
  "hermes-agent": {
    name: "hermes-agent", displayName: "Hermes Agent",
    skillsDir: ".hermes/skills",
    globalSkillsDir: path.join(home, ".hermes/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".hermes")),
  },
  junie: {
    name: "junie", displayName: "Junie",
    skillsDir: ".junie/skills",
    globalSkillsDir: path.join(home, ".junie/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".junie")),
  },
  "iflow-cli": {
    name: "iflow-cli", displayName: "iFlow CLI",
    skillsDir: ".iflow/skills",
    globalSkillsDir: path.join(home, ".iflow/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".iflow")),
  },
  kilo: {
    name: "kilo", displayName: "Kilo Code",
    skillsDir: ".kilocode/skills",
    globalSkillsDir: path.join(home, ".kilocode/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".kilocode")),
  },
  "kimi-cli": {
    name: "kimi-cli", displayName: "Kimi Code CLI",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".config/agents/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".kimi")),
  },
  "kiro-cli": {
    name: "kiro-cli", displayName: "Kiro CLI",
    skillsDir: ".kiro/skills",
    globalSkillsDir: path.join(home, ".kiro/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".kiro")),
  },
  kode: {
    name: "kode", displayName: "Kode",
    skillsDir: ".kode/skills",
    globalSkillsDir: path.join(home, ".kode/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".kode")),
  },
  mcpjam: {
    name: "mcpjam", displayName: "MCPJam",
    skillsDir: ".mcpjam/skills",
    globalSkillsDir: path.join(home, ".mcpjam/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".mcpjam")),
  },
  "mistral-vibe": {
    name: "mistral-vibe", displayName: "Mistral Vibe",
    skillsDir: ".vibe/skills",
    globalSkillsDir: path.join(vibeHome, "skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(vibeHome),
  },
  mux: {
    name: "mux", displayName: "Mux",
    skillsDir: ".mux/skills",
    globalSkillsDir: path.join(home, ".mux/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".mux")),
  },
  opencode: {
    name: "opencode", displayName: "OpenCode",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(configHome, "opencode/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(configHome, "opencode")),
  },
  openhands: {
    name: "openhands", displayName: "OpenHands",
    skillsDir: ".openhands/skills",
    globalSkillsDir: path.join(home, ".openhands/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".openhands")),
  },
  pi: {
    name: "pi", displayName: "Pi",
    skillsDir: ".pi/skills",
    globalSkillsDir: path.join(home, ".pi/agent/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".pi/agent")),
  },
  qoder: {
    name: "qoder", displayName: "Qoder",
    skillsDir: ".qoder/skills",
    globalSkillsDir: path.join(home, ".qoder/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".qoder")),
  },
  "qwen-code": {
    name: "qwen-code", displayName: "Qwen Code",
    skillsDir: ".qwen/skills",
    globalSkillsDir: path.join(home, ".qwen/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".qwen")),
  },
  replit: {
    name: "replit", displayName: "Replit",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(configHome, "agents/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    showInUniversalList: false,
    detectInstalled: () => fs.existsSync(path.join(process.cwd(), ".replit")),
  },
  rovodev: {
    name: "rovodev", displayName: "Rovo Dev",
    skillsDir: ".rovodev/skills",
    globalSkillsDir: path.join(home, ".rovodev/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".rovodev")),
  },
  roo: {
    name: "roo", displayName: "Roo Code",
    skillsDir: ".roo/skills",
    globalSkillsDir: path.join(home, ".roo/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".roo")),
  },
  "tabnine-cli": {
    name: "tabnine-cli", displayName: "Tabnine CLI",
    skillsDir: ".tabnine/agent/skills",
    globalSkillsDir: path.join(home, ".tabnine/agent/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".tabnine")),
  },
  trae: {
    name: "trae", displayName: "Trae",
    skillsDir: ".trae/skills",
    globalSkillsDir: path.join(home, ".trae/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".trae")),
  },
  "trae-cn": {
    name: "trae-cn", displayName: "Trae CN",
    skillsDir: ".trae/skills",
    globalSkillsDir: path.join(home, ".trae-cn/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".trae-cn")),
  },
  warp: {
    name: "warp", displayName: "Warp",
    skillsDir: ".agents/skills",
    globalSkillsDir: path.join(home, ".agents/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".warp")),
  },
  windsurf: {
    name: "windsurf", displayName: "Windsurf",
    skillsDir: ".windsurf/skills",
    globalSkillsDir: path.join(home, ".codeium/windsurf/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".codeium/windsurf")),
  },
  zencoder: {
    name: "zencoder", displayName: "Zencoder",
    skillsDir: ".zencoder/skills",
    globalSkillsDir: path.join(home, ".zencoder/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".zencoder")),
  },
  neovate: {
    name: "neovate", displayName: "Neovate",
    skillsDir: ".neovate/skills",
    globalSkillsDir: path.join(home, ".neovate/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".neovate")),
  },
  pochi: {
    name: "pochi", displayName: "Pochi",
    skillsDir: ".pochi/skills",
    globalSkillsDir: path.join(home, ".pochi/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".pochi")),
  },
  adal: {
    name: "adal", displayName: "AdaL",
    skillsDir: ".adal/skills",
    globalSkillsDir: path.join(home, ".adal/skills"),
    ruleFile: "AGENTS.md", ruleFormat: "boilerplate", appendOk: true,
    detectInstalled: () => fs.existsSync(path.join(home, ".adal")),
  },
};

export function detectInstalledAgents(): AgentId[] {
  return Object.entries(AGENTS)
    .filter(([_, c]) => {
      try { return c.detectInstalled(); } catch { return false; }
    })
    .map(([id]) => id);
}

export function isUniversalAgent(id: AgentId): boolean {
  return AGENTS[id]?.skillsDir === ".agents/skills";
}

export function getAgent(id: AgentId): AgentConfig | undefined {
  return AGENTS[id];
}
